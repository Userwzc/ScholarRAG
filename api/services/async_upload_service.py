import asyncio
from concurrent.futures import Executor, ProcessPoolExecutor, ThreadPoolExecutor
import hashlib
import os
import re
import shutil
import threading
import time
import uuid
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import API_UPLOAD_DIR
from api.models import IngestionJob
from api.schemas import (
    IngestionJobCreateResponse,
    IngestionJobListItem,
    IngestionJobListResponse,
    IngestionJobResponse,
    IngestionJobResult,
    IngestionJobRetryResponse,
)
from api.services import ingestion_job_service, paper_registry_service

STAGED_UPLOADS_DIR = os.path.join(API_UPLOAD_DIR, "staged")
_LEGACY_JOB_GUARD_LOCK = threading.Lock()
_LEGACY_GUARDED_JOB_IDS: set[str] = set()
_EXECUTOR_LOCK = threading.Lock()
_BACKGROUND_EXECUTOR: Optional[Executor] = None


def _get_vector_store():
    from src.rag.vector_store import get_vector_store

    return get_vector_store()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _generate_job_id(filename: str) -> str:
    timestamp = str(time.time())
    unique_input = f"{filename}-{timestamp}-{uuid.uuid4()}"
    return hashlib.sha256(unique_input.encode()).hexdigest()[:16]


def _calculate_file_hash(file_path: str) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _ensure_staged_dir() -> None:
    os.makedirs(STAGED_UPLOADS_DIR, exist_ok=True)


def _sanitize_error_message(error: Exception) -> str:
    normalized = re.sub(r"\s+", " ", str(error)).strip()
    if not normalized:
        normalized = "Ingestion failed"
    return normalized[:500]


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    return normalized in ("1", "true", "yes", "on")


def _use_db_job_lease() -> bool:
    return _parse_bool_env("USE_DB_JOB_LEASE", False)


def _get_job_lease_ttl_ms() -> int:
    raw = os.getenv("JOB_LEASE_TTL_SECONDS", "300")
    try:
        seconds = int(raw)
    except ValueError:
        seconds = 300
    return max(1, seconds) * 1000


def _get_executor_type() -> str:
    raw = os.getenv("EXECUTOR_TYPE", "thread").strip().lower()
    if raw not in ("thread", "process"):
        return "thread"
    return raw


def _get_background_workers() -> int:
    raw = os.getenv("BACKGROUND_EXECUTOR_WORKERS", "2")
    try:
        workers = int(raw)
    except ValueError:
        workers = 2
    cpu_count = os.cpu_count() or 2
    return max(1, min(workers, cpu_count))


def _get_background_executor() -> Executor:
    global _BACKGROUND_EXECUTOR
    if _BACKGROUND_EXECUTOR is not None:
        return _BACKGROUND_EXECUTOR

    with _EXECUTOR_LOCK:
        if _BACKGROUND_EXECUTOR is not None:
            return _BACKGROUND_EXECUTOR

        workers = _get_background_workers()
        if _get_executor_type() == "process":
            _BACKGROUND_EXECUTOR = ProcessPoolExecutor(max_workers=workers)
        else:
            _BACKGROUND_EXECUTOR = ThreadPoolExecutor(max_workers=workers)
        return _BACKGROUND_EXECUTOR


def _create_lease_owner() -> str:
    return f"{os.getpid()}-{uuid.uuid4().hex}"


def _try_acquire_legacy_job_guard(job_id: str) -> bool:
    with _LEGACY_JOB_GUARD_LOCK:
        if job_id in _LEGACY_GUARDED_JOB_IDS:
            return False
        _LEGACY_GUARDED_JOB_IDS.add(job_id)
        return True


def _release_legacy_job_guard(job_id: str) -> None:
    with _LEGACY_JOB_GUARD_LOCK:
        _LEGACY_GUARDED_JOB_IDS.discard(job_id)


async def _try_acquire_db_lease(
    session: AsyncSession,
    job_id: str,
    lease_owner: str,
) -> bool:
    now = _now_ms()
    expired_before = now - _get_job_lease_ttl_ms()
    result = await session.execute(
        text(
            """
            UPDATE ingestion_jobs
            SET status = 'processing',
                leased_at = :now,
                leased_by = :lease_owner,
                updated_at = :now
            WHERE id = :job_id
              AND (
                (status = 'pending' AND (leased_at IS NULL OR leased_at < :expired_before))
                OR (status = 'processing' AND leased_at IS NOT NULL AND leased_at < :expired_before)
              )
            """
        ),
        {
            "job_id": job_id,
            "now": now,
            "lease_owner": lease_owner,
            "expired_before": expired_before,
        },
    )
    await session.flush()
    return (result.rowcount or 0) > 0


async def _refresh_db_lease(
    session: AsyncSession,
    job_id: str,
    lease_owner: str,
) -> None:
    now = _now_ms()
    await session.execute(
        text(
            """
            UPDATE ingestion_jobs
            SET leased_at = :now,
                updated_at = :now
            WHERE id = :job_id AND leased_by = :lease_owner
            """
        ),
        {"job_id": job_id, "lease_owner": lease_owner, "now": now},
    )
    await session.flush()


async def _release_db_lease(
    session: AsyncSession,
    job_id: str,
    lease_owner: str,
) -> None:
    now = _now_ms()
    await session.execute(
        text(
            """
            UPDATE ingestion_jobs
            SET leased_at = NULL,
                leased_by = NULL,
                updated_at = :now
            WHERE id = :job_id AND leased_by = :lease_owner
            """
        ),
        {"job_id": job_id, "lease_owner": lease_owner, "now": now},
    )
    await session.flush()


async def _acquire_job_guard(session: AsyncSession, job_id: str) -> Optional[str]:
    if _use_db_job_lease():
        lease_owner = _create_lease_owner()
        if await _try_acquire_db_lease(session, job_id, lease_owner):
            return lease_owner
        return None

    if _try_acquire_legacy_job_guard(job_id):
        return "legacy"
    return None


async def _release_job_guard_safe(
    session: AsyncSession,
    job_id: str,
    lease_owner: Optional[str],
) -> None:
    if lease_owner is None:
        return

    if _use_db_job_lease() and lease_owner != "legacy":
        await _release_db_lease(session, job_id, lease_owner)
        return

    _release_legacy_job_guard(job_id)


def stage_uploaded_file(file_content: bytes, filename: str, job_id: str) -> str:
    _ensure_staged_dir()
    job_dir = os.path.join(STAGED_UPLOADS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    file_path = os.path.join(job_dir, filename)
    with open(file_path, "wb") as f:
        f.write(file_content)
    return file_path


def cleanup_staged_file(job_id: str) -> None:
    job_dir = os.path.join(STAGED_UPLOADS_DIR, job_id)
    if os.path.exists(job_dir):
        shutil.rmtree(job_dir)


async def create_async_upload_job(
    session: AsyncSession,
    file_content: bytes,
    filename: str,
) -> IngestionJobCreateResponse:
    job_id = _generate_job_id(filename)
    staged_path = stage_uploaded_file(file_content, filename, job_id)

    pdf_name = os.path.splitext(filename)[0]
    paper = await paper_registry_service.create_or_get_paper(
        session=session,
        pdf_name=pdf_name,
        title=pdf_name,
        authors="",
    )

    job = await ingestion_job_service.create_ingestion_job(
        session=session,
        job_id=job_id,
        paper_id=paper.id,
        source_file_path=staged_path,
        status="pending",
        stage="queued",
        progress=0,
    )

    return IngestionJobCreateResponse(
        job_id=job.id,
        status=job.status,
        filename=filename,
        message="Upload accepted. Processing started.",
    )


async def create_reindex_job(
    session: AsyncSession,
    pdf_name: str,
) -> Optional[IngestionJobCreateResponse]:
    from api.services import paper_service

    paper = await paper_registry_service.get_paper_by_pdf_name(session, pdf_name)
    if paper is None:
        return None

    source_pdf = os.path.join(paper_service.PDF_STORAGE_DIR, f"{pdf_name}.pdf")
    if not os.path.exists(source_pdf):
        return None

    with open(source_pdf, "rb") as f:
        file_content = f.read()

    filename = f"{pdf_name}.pdf"
    job_id = _generate_job_id(filename)
    staged_path = stage_uploaded_file(file_content, filename, job_id)

    job = await ingestion_job_service.create_ingestion_job(
        session=session,
        job_id=job_id,
        paper_id=paper.id,
        source_file_path=staged_path,
        status="pending",
        stage="queued",
        progress=0,
    )

    return IngestionJobCreateResponse(
        job_id=job.id,
        status=job.status,
        filename=filename,
        message="Reindex accepted. Processing started.",
    )


async def get_job_status(
    session: AsyncSession,
    job_id: str,
) -> Optional[IngestionJobResponse]:
    job = await ingestion_job_service.get_ingestion_job(session, job_id)
    if job is None:
        return None

    result: Optional[IngestionJobResult] = None
    if job.status == "completed" and job.result_summary:
        import json

        try:
            result_data = json.loads(job.result_summary)
            result = IngestionJobResult(**result_data)
        except (json.JSONDecodeError, TypeError):
            pass

    return IngestionJobResponse(
        job_id=job.id,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        retry_count=job.retry_count,
        error_message=job.error_message,
        result=result,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


async def list_recent_jobs(
    session: AsyncSession,
    limit: int = 20,
) -> IngestionJobListResponse:
    from sqlalchemy.orm import selectinload

    result = await session.execute(
        select(IngestionJob)
        .options(selectinload(IngestionJob.paper))
        .order_by(IngestionJob.created_at.desc())
        .limit(limit)
    )
    jobs = list(result.scalars().all())

    items = [
        IngestionJobListItem(
            job_id=job.id,
            pdf_name=job.paper.pdf_name if job.paper else "",
            status=job.status,
            stage=job.stage,
            progress=job.progress,
            retry_count=job.retry_count,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
        for job in jobs
    ]

    return IngestionJobListResponse(jobs=items, total=len(items))


async def retry_failed_job(
    session: AsyncSession,
    job_id: str,
) -> Optional[IngestionJobRetryResponse]:
    job = await ingestion_job_service.get_ingestion_job(session, job_id)
    if job is None:
        return None

    if job.status != "failed":
        return None

    if not os.path.exists(job.source_file_path):
        await ingestion_job_service.update_ingestion_job(
            session=session,
            job_id=job_id,
            status="failed",
            error_message="Source file no longer available for retry",
        )
        return IngestionJobRetryResponse(
            job_id=job_id,
            status="failed",
            message="Source file no longer available for retry",
        )

    await ingestion_job_service.update_ingestion_job(
        session=session,
        job_id=job_id,
        status="pending",
        stage="queued",
        progress=0,
        error_message=None,
        leased_at=None,
        leased_by=None,
    )
    await ingestion_job_service.increment_retry_count(session, job_id)

    return IngestionJobRetryResponse(
        job_id=job_id,
        status="pending",
        message="Job queued for retry",
    )


async def run_ingestion_job(
    session: AsyncSession,
    job_id: str,
) -> None:
    from api.services import paper_service
    from src.core.ingestion import INGESTION_SCHEMA_VERSION

    lease_owner = await _acquire_job_guard(session, job_id)
    if lease_owner is None:
        return

    try:
        job = await ingestion_job_service.get_ingestion_job(session, job_id)
        if job is None:
            return

        if not _use_db_job_lease():
            if job.status == "processing":
                return

            if job.status != "pending":
                return

        async def _update_job_progress(stage: str, progress: int) -> None:
            kwargs = {
                "session": session,
                "job_id": job_id,
                "status": "processing",
                "stage": stage,
                "progress": progress,
                "error_message": None,
            }

            if _use_db_job_lease() and lease_owner != "legacy":
                kwargs["leased_at"] = _now_ms()
                kwargs["leased_by"] = lease_owner

            await ingestion_job_service.update_ingestion_job(
                **kwargs,
            )

            if _use_db_job_lease() and lease_owner != "legacy":
                await _refresh_db_lease(session, job_id, lease_owner)

        await _update_job_progress("parsing", 10)

        source_hash = _calculate_file_hash(job.source_file_path)
        paper_version = await paper_registry_service.create_paper_version(
            session=session,
            paper_id=job.paper_id,
            source_hash=source_hash,
            ingestion_schema_version=INGESTION_SCHEMA_VERSION,
        )
        await ingestion_job_service.update_ingestion_job(
            session=session,
            job_id=job_id,
            paper_version_id=paper_version.id,
        )

        loop = asyncio.get_running_loop()

        def _progress_callback(stage: str, progress: int) -> None:
            future = asyncio.run_coroutine_threadsafe(
                _update_job_progress(stage, progress),
                loop,
            )
            future.result()

        ingest_result = await asyncio.to_thread(
            paper_service.ingest_paper_file,
            file_path=job.source_file_path,
            save_markdown=False,
            progress_callback=_progress_callback,
            paper_version=paper_version.version_number,
            is_current=True,
        )

        pdf_name = ingest_result["pdf_name"]
        paper_title = ingest_result["title"]
        authors_str = ingest_result["authors"]
        chunk_count = ingest_result["chunk_count"]

        _get_vector_store().mark_paper_chunks_non_current(
            pdf_name=pdf_name,
            keep_version=paper_version.version_number,
        )

        paper = await paper_registry_service.get_paper_by_pdf_name(session, pdf_name)
        if paper:
            paper.title = paper_title
            paper.authors = authors_str
            paper.updated_at = _now_ms()
            await session.flush()

        import json

        result_summary = json.dumps(
            {
                "pdf_name": pdf_name,
                "title": paper_title,
                "authors": authors_str,
                "chunk_count": chunk_count,
                "paper_version": paper_version.version_number,
            }
        )

        await ingestion_job_service.update_ingestion_job(
            session=session,
            job_id=job_id,
            status="completed",
            stage="completed",
            progress=100,
            result_summary=result_summary,
            error_message=None,
        )

        cleanup_staged_file(job_id)

    except Exception as error:
        await ingestion_job_service.update_ingestion_job(
            session=session,
            job_id=job_id,
            status="failed",
            stage="failed",
            error_message=_sanitize_error_message(error),
        )
    finally:
        await _release_job_guard_safe(session, job_id, lease_owner)


async def run_ingestion_job_background(job_id: str) -> None:
    from api.database import async_session_maker

    async with async_session_maker() as session:
        try:
            await run_ingestion_job(session, job_id)
            await session.commit()
        except Exception:  # noqa: S110 - Session rollback needs to catch broad exceptions
            await session.rollback()
            raise


def _run_ingestion_job_background_sync(job_id: str) -> None:
    asyncio.run(run_ingestion_job_background(job_id))


def start_background_ingestion(job_id: str) -> None:
    _get_background_executor().submit(_run_ingestion_job_background_sync, job_id)
