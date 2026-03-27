import asyncio
import hashlib
import os
import shutil
import time
import uuid
from typing import Optional

from sqlalchemy import select
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
from config.settings import config

STAGED_UPLOADS_DIR = os.path.join(API_UPLOAD_DIR, "staged")
PDF_STORAGE_DIR = config.PDF_STORAGE_DIR


def _now_ms() -> int:
    return int(time.time() * 1000)


def _generate_job_id(filename: str) -> str:
    timestamp = str(time.time())
    unique_input = f"{filename}-{timestamp}-{uuid.uuid4()}"
    return hashlib.sha256(unique_input.encode()).hexdigest()[:16]


def _ensure_staged_dir() -> None:
    os.makedirs(STAGED_UPLOADS_DIR, exist_ok=True)


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
    from src.core.ingestion import process_paper

    job = await ingestion_job_service.get_ingestion_job(session, job_id)
    if job is None:
        return

    if job.status not in ("pending", "processing"):
        return

    try:
        await ingestion_job_service.update_ingestion_job(
            session=session,
            job_id=job_id,
            status="processing",
            stage="parsing",
            progress=10,
        )

        multimodal_inputs, metadata_list, parsed_data = process_paper(
            job.source_file_path, save_markdown=False
        )

        await ingestion_job_service.update_ingestion_job(
            session=session,
            job_id=job_id,
            stage="storing",
            progress=50,
        )

        pdf_name = parsed_data.get("pdf_name", "")
        paper_title = parsed_data.get("title", "Unknown Title")
        authors_str = ""
        if metadata_list:
            authors_str = metadata_list[0].get("authors", "")
            paper_title = metadata_list[0].get("title", paper_title)

        paper = await paper_registry_service.get_paper_by_pdf_name(session, pdf_name)
        if paper:
            paper.title = paper_title
            paper.authors = authors_str
            paper.updated_at = _now_ms()
            await session.flush()

        os.makedirs(PDF_STORAGE_DIR, exist_ok=True)
        pdf_dest = os.path.join(PDF_STORAGE_DIR, f"{pdf_name}.pdf")
        if os.path.exists(job.source_file_path) and not os.path.exists(pdf_dest):
            shutil.copy(job.source_file_path, pdf_dest)

        await ingestion_job_service.update_ingestion_job(
            session=session,
            job_id=job_id,
            stage="indexing",
            progress=70,
        )

        from src.rag.vector_store import get_vector_store

        vector_store = get_vector_store()
        vector_store.add_multimodal(multimodal_inputs, metadata_list)

        import json

        result_summary = json.dumps(
            {
                "pdf_name": pdf_name,
                "title": paper_title,
                "authors": authors_str,
                "chunk_count": len(multimodal_inputs),
            }
        )

        await ingestion_job_service.update_ingestion_job(
            session=session,
            job_id=job_id,
            status="completed",
            stage="completed",
            progress=100,
            result_summary=result_summary,
        )

        cleanup_staged_file(job_id)

    except Exception as e:
        error_msg = str(e)
        if len(error_msg) > 500:
            error_msg = error_msg[:500]

        await ingestion_job_service.update_ingestion_job(
            session=session,
            job_id=job_id,
            status="failed",
            stage="failed",
            error_message=error_msg,
        )


async def run_ingestion_job_background(job_id: str) -> None:
    from api.database import async_session_maker

    async with async_session_maker() as session:
        try:
            await run_ingestion_job(session, job_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def start_background_ingestion(job_id: str) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_ingestion_job_background(job_id))
    finally:
        loop.close()
