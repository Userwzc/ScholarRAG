import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import IngestionJob

TERMINAL_JOB_STATUSES = ("completed", "failed")
ACTIVE_JOB_STATUSES = ("pending", "processing")
VALID_JOB_STATUSES = ACTIVE_JOB_STATUSES + TERMINAL_JOB_STATUSES


def _now_ms() -> int:
    return int(time.time() * 1000)


def _normalize_job_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in VALID_JOB_STATUSES:
        raise ValueError(f"Invalid job status: {status}")
    return normalized


async def create_ingestion_job(
    session: AsyncSession,
    job_id: str,
    paper_id: int,
    source_file_path: str,
    paper_version_id: Optional[int] = None,
    status: str = "pending",
    stage: str = "queued",
    progress: int = 0,
) -> IngestionJob:
    now = _now_ms()
    job = IngestionJob(
        id=job_id,
        paper_id=paper_id,
        paper_version_id=paper_version_id,
        status=_normalize_job_status(status),
        stage=stage,
        progress=max(0, min(progress, 100)),
        retry_count=0,
        source_file_path=source_file_path,
        result_summary=None,
        error_message=None,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.flush()
    return job


async def get_ingestion_job(session: AsyncSession, job_id: str) -> Optional[IngestionJob]:
    result = await session.execute(select(IngestionJob).where(IngestionJob.id == job_id))
    return result.scalar_one_or_none()


async def list_ingestion_jobs_by_paper(
    session: AsyncSession,
    paper_id: int,
) -> list[IngestionJob]:
    result = await session.execute(
        select(IngestionJob)
        .where(IngestionJob.paper_id == paper_id)
        .order_by(IngestionJob.created_at.desc())
    )
    return list(result.scalars().all())


async def update_ingestion_job(
    session: AsyncSession,
    job_id: str,
    status: Optional[str] = None,
    stage: Optional[str] = None,
    progress: Optional[int] = None,
    retry_count: Optional[int] = None,
    paper_version_id: Optional[int] = None,
    result_summary: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Optional[IngestionJob]:
    job = await get_ingestion_job(session, job_id)
    if job is None:
        return None

    if status is not None:
        job.status = _normalize_job_status(status)
    if stage is not None:
        job.stage = stage
    if progress is not None:
        job.progress = max(0, min(progress, 100))
    if retry_count is not None:
        job.retry_count = max(0, retry_count)
    if paper_version_id is not None:
        job.paper_version_id = paper_version_id
    if result_summary is not None:
        job.result_summary = result_summary
    if error_message is not None:
        job.error_message = error_message

    job.updated_at = _now_ms()
    await session.flush()
    return job


async def increment_retry_count(
    session: AsyncSession,
    job_id: str,
) -> Optional[IngestionJob]:
    job = await get_ingestion_job(session, job_id)
    if job is None:
        return None

    job.retry_count += 1
    job.updated_at = _now_ms()
    await session.flush()
    return job
