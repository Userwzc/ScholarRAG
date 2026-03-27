import json
import os

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")

from sqlalchemy.ext.asyncio import AsyncSession  # type: ignore[reportMissingImports]  # noqa: E402

from api.schemas import (  # noqa: E402
    IngestionJobCreateResponse,
    IngestionJobListResponse,
    IngestionJobResponse,
    IngestionJobRetryResponse,
)
from api.services import async_upload_service  # noqa: E402
from api.services.ingestion_job_service import get_ingestion_job, update_ingestion_job  # noqa: E402
from api.services.paper_registry_service import create_or_get_paper  # noqa: E402


@pytest.mark.asyncio
async def test_create_async_upload_job_returns_job_id(db_session: AsyncSession) -> None:
    file_content = b"%PDF-1.4 test content"
    filename = "test-paper.pdf"

    result = await async_upload_service.create_async_upload_job(
        session=db_session,
        file_content=file_content,
        filename=filename,
    )

    assert isinstance(result, IngestionJobCreateResponse)
    assert result.job_id != ""
    assert result.status == "pending"
    assert result.filename == filename
    assert "accepted" in result.message.lower()

    job = await get_ingestion_job(db_session, result.job_id)
    assert job is not None
    assert job.status == "pending"
    assert job.stage == "queued"
    assert job.progress == 0

    assert os.path.exists(job.source_file_path)


@pytest.mark.asyncio
async def test_get_job_status_returns_full_job_info(db_session: AsyncSession) -> None:
    await create_or_get_paper(
        db_session,
        pdf_name="status-test-paper",
        title="Status Test Paper",
        authors="Test Author",
    )

    file_content = b"%PDF-1.4 test content"
    filename = "status-test-paper.pdf"

    create_result = await async_upload_service.create_async_upload_job(
        session=db_session,
        file_content=file_content,
        filename=filename,
    )

    await update_ingestion_job(
        db_session,
        job_id=create_result.job_id,
        status="processing",
        stage="parsing",
        progress=30,
    )

    status = await async_upload_service.get_job_status(db_session, create_result.job_id)

    assert status is not None
    assert isinstance(status, IngestionJobResponse)
    assert status.job_id == create_result.job_id
    assert status.status == "processing"
    assert status.stage == "parsing"
    assert status.progress == 30
    assert status.retry_count == 0
    assert status.error_message is None
    assert status.result is None


@pytest.mark.asyncio
async def test_get_job_status_includes_result_for_completed_job(
    db_session: AsyncSession,
) -> None:
    await create_or_get_paper(
        db_session,
        pdf_name="completed-paper",
        title="Completed Paper",
        authors="Test Author",
    )

    file_content = b"%PDF-1.4 test content"
    filename = "completed-paper.pdf"

    create_result = await async_upload_service.create_async_upload_job(
        session=db_session,
        file_content=file_content,
        filename=filename,
    )

    result_summary = json.dumps(
        {
            "pdf_name": "completed-paper",
            "title": "Completed Paper",
            "authors": "Test Author",
            "chunk_count": 10,
        }
    )

    await update_ingestion_job(
        db_session,
        job_id=create_result.job_id,
        status="completed",
        stage="completed",
        progress=100,
        result_summary=result_summary,
    )

    status = await async_upload_service.get_job_status(db_session, create_result.job_id)

    assert status is not None
    assert status.status == "completed"
    assert status.result is not None
    assert status.result.pdf_name == "completed-paper"
    assert status.result.chunk_count == 10


@pytest.mark.asyncio
async def test_list_recent_jobs_returns_jobs(db_session: AsyncSession) -> None:
    for i in range(3):
        file_content = b"%PDF-1.4 test content"
        filename = f"list-test-paper-{i}.pdf"

        await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=file_content,
            filename=filename,
        )

    result = await async_upload_service.list_recent_jobs(db_session, limit=10)

    assert isinstance(result, IngestionJobListResponse)
    assert len(result.jobs) == 3
    assert result.total == 3

    for job in result.jobs:
        assert job.job_id != ""
        assert job.status in ("pending", "processing", "completed", "failed")


@pytest.mark.asyncio
async def test_retry_failed_job_resets_status(db_session: AsyncSession) -> None:
    file_content = b"%PDF-1.4 test content"
    filename = "retry-test-paper.pdf"

    create_result = await async_upload_service.create_async_upload_job(
        session=db_session,
        file_content=file_content,
        filename=filename,
    )

    await update_ingestion_job(
        db_session,
        job_id=create_result.job_id,
        status="failed",
        stage="failed",
        error_message="Test error",
    )

    retry_result = await async_upload_service.retry_failed_job(
        db_session, create_result.job_id
    )

    assert retry_result is not None
    assert isinstance(retry_result, IngestionJobRetryResponse)
    assert retry_result.job_id == create_result.job_id
    assert retry_result.status == "pending"
    assert "retry" in retry_result.message.lower()

    job = await get_ingestion_job(db_session, create_result.job_id)
    assert job is not None
    assert job.status == "pending"
    assert job.stage == "queued"
    assert job.retry_count == 1


@pytest.mark.asyncio
async def test_retry_non_failed_job_returns_none(db_session: AsyncSession) -> None:
    file_content = b"%PDF-1.4 test content"
    filename = "no-retry-paper.pdf"

    create_result = await async_upload_service.create_async_upload_job(
        session=db_session,
        file_content=file_content,
        filename=filename,
    )

    retry_result = await async_upload_service.retry_failed_job(
        db_session, create_result.job_id
    )

    assert retry_result is None


@pytest.mark.asyncio
async def test_get_job_status_returns_none_for_nonexistent_job(
    db_session: AsyncSession,
) -> None:
    status = await async_upload_service.get_job_status(db_session, "nonexistent-job-id")
    assert status is None


@pytest.mark.asyncio
async def test_staged_file_persists_after_job_creation(
    db_session: AsyncSession,
) -> None:
    file_content = b"%PDF-1.4 unique test content for persistence check"
    filename = "persistence-test.pdf"

    create_result = await async_upload_service.create_async_upload_job(
        session=db_session,
        file_content=file_content,
        filename=filename,
    )

    job = await get_ingestion_job(db_session, create_result.job_id)
    assert job is not None
    assert os.path.exists(job.source_file_path)

    with open(job.source_file_path, "rb") as f:
        saved_content = f.read()
    assert saved_content == file_content


@pytest.mark.asyncio
async def test_cleanup_staged_file_removes_directory(db_session: AsyncSession) -> None:
    file_content = b"%PDF-1.4 test content"
    filename = "cleanup-test.pdf"

    create_result = await async_upload_service.create_async_upload_job(
        session=db_session,
        file_content=file_content,
        filename=filename,
    )

    job = await get_ingestion_job(db_session, create_result.job_id)
    assert job is not None
    staged_path = job.source_file_path
    job_dir = os.path.dirname(staged_path)

    assert os.path.exists(staged_path)

    async_upload_service.cleanup_staged_file(create_result.job_id)

    assert not os.path.exists(job_dir)
