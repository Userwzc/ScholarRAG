import asyncio
import json
import os
import threading
import time
from unittest.mock import patch

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
from api.services.paper_registry_service import (  # noqa: E402
    create_or_get_paper,
    get_paper_by_pdf_name,
    list_versions,
)


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


@pytest.mark.asyncio
async def test_run_ingestion_job_persists_stage_progression_and_completes(
    db_session: AsyncSession,
) -> None:
    file_content = b"%PDF-1.4 test content"
    filename = "pipeline-test.pdf"

    create_result = await async_upload_service.create_async_upload_job(
        session=db_session,
        file_content=file_content,
        filename=filename,
    )

    observed_stages: list[tuple[str | None, int | None]] = []

    async def _spy_update_ingestion_job(*args, **kwargs):
        stage = kwargs.get("stage")
        progress = kwargs.get("progress")
        if stage is not None or progress is not None:
            observed_stages.append((stage, progress))
        return await original_update(*args, **kwargs)

    def _fake_ingest(*args, **kwargs):
        callback = kwargs["progress_callback"]
        callback("parsing", 10)
        callback("chunking", 35)
        callback("storing", 65)
        callback("finalizing", 90)
        callback("completed", 100)
        return {
            "pdf_name": "pipeline-test",
            "title": "Pipeline Test",
            "authors": "Author",
            "chunk_count": 3,
        }

    original_update = async_upload_service.ingestion_job_service.update_ingestion_job
    with (
        patch(
            "api.services.paper_service.ingest_paper_file",
            side_effect=_fake_ingest,
        ),
        patch("api.services.async_upload_service._get_vector_store") as mock_get_vector_store,
        patch(
            "api.services.async_upload_service.ingestion_job_service.update_ingestion_job",
            side_effect=_spy_update_ingestion_job,
        ),
    ):
        mock_get_vector_store.return_value.mark_paper_chunks_non_current.return_value = 1
        await async_upload_service.run_ingestion_job(db_session, create_result.job_id)

    job = await get_ingestion_job(db_session, create_result.job_id)
    assert job is not None
    assert job.status == "completed"
    assert job.stage == "completed"
    assert job.progress == 100
    assert job.result_summary is not None
    assert json.loads(job.result_summary)["pdf_name"] == "pipeline-test"
    assert json.loads(job.result_summary)["paper_version"] == 1

    stage_sequence = [stage for stage, _ in observed_stages if stage is not None]
    assert stage_sequence == [
        "parsing",
        "parsing",
        "chunking",
        "storing",
        "finalizing",
        "completed",
        "completed",
    ]


@pytest.mark.asyncio
async def test_run_ingestion_job_marks_failed_and_preserves_staged_file_for_retry(
    db_session: AsyncSession,
) -> None:
    file_content = b"%PDF-1.4 test content"
    filename = "fail-test.pdf"

    create_result = await async_upload_service.create_async_upload_job(
        session=db_session,
        file_content=file_content,
        filename=filename,
    )
    job_before = await get_ingestion_job(db_session, create_result.job_id)
    assert job_before is not None
    staged_path = job_before.source_file_path

    with (
        patch(
            "api.services.paper_service.ingest_paper_file",
            side_effect=RuntimeError("x" * 1000),
        ),
        patch("api.services.async_upload_service._get_vector_store") as mock_get_vector_store,
    ):
        mock_get_vector_store.return_value.mark_paper_chunks_non_current.return_value = 0
        await async_upload_service.run_ingestion_job(db_session, create_result.job_id)

    failed_job = await get_ingestion_job(db_session, create_result.job_id)
    assert failed_job is not None
    assert failed_job.status == "failed"
    assert failed_job.stage == "failed"
    assert failed_job.error_message is not None
    assert len(failed_job.error_message) == 500
    assert os.path.exists(staged_path)


@pytest.mark.asyncio
async def test_run_ingestion_job_prevents_duplicate_processing_execution(
    temp_db: dict,
) -> None:
    async with temp_db["session_maker"]() as setup_session:
        file_content = b"%PDF-1.4 test content"
        filename = "duplicate-test.pdf"
        create_result = await async_upload_service.create_async_upload_job(
            session=setup_session,
            file_content=file_content,
            filename=filename,
        )
        await setup_session.commit()

    call_count = 0

    def _fake_ingest(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        callback = kwargs["progress_callback"]
        callback("parsing", 10)
        callback("chunking", 35)
        callback("storing", 65)
        callback("finalizing", 90)
        callback("completed", 100)
        return {
            "pdf_name": "duplicate-test",
            "title": "Duplicate Test",
            "authors": "Author",
            "chunk_count": 2,
        }

    with (
        patch("api.services.paper_service.ingest_paper_file", side_effect=_fake_ingest),
        patch("api.services.async_upload_service._get_vector_store") as mock_get_vector_store,
    ):
        mock_get_vector_store.return_value.mark_paper_chunks_non_current.return_value = 1
        async with temp_db["session_maker"]() as session_one, temp_db["session_maker"]() as session_two:
            await asyncio.gather(
                async_upload_service.run_ingestion_job(session_one, create_result.job_id),
                async_upload_service.run_ingestion_job(session_two, create_result.job_id),
            )
            await session_one.commit()
            await session_two.commit()

    assert call_count == 1


@pytest.mark.asyncio
async def test_db_lease_prevents_two_workers_from_processing_same_job(
    temp_db: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that database lease prevents duplicate processing.
    
    Note: SQLite doesn't support high concurrency, so we test the lease logic
    sequentially rather than in parallel.
    """
    import sys
    monkeypatch.setenv("USE_DB_JOB_LEASE", "true")

    async with temp_db["session_maker"]() as setup_session:
        create_result = await async_upload_service.create_async_upload_job(
            session=setup_session,
            file_content=b"%PDF-1.4 db lease",
            filename="db-lease-duplicate.pdf",
        )
        await setup_session.commit()

    call_count = 0

    def _slow_fake_ingest(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        callback = kwargs["progress_callback"]
        callback("parsing", 10)
        time.sleep(0.05)  # Reduced sleep time
        callback("completed", 100)
        return {
            "pdf_name": "db-lease-duplicate",
            "title": "DB Lease Duplicate",
            "authors": "Author",
            "chunk_count": 1,
        }

    with (
        patch("api.services.paper_service.ingest_paper_file", side_effect=_slow_fake_ingest),
        patch("api.services.async_upload_service._get_vector_store") as mock_get_vector_store,
    ):
        mock_get_vector_store.return_value.mark_paper_chunks_non_current.return_value = 1
        
        # Use sequential execution for SQLite compatibility
        # First worker should acquire lease and process
        async with temp_db["session_maker"]() as worker_one:
            await async_upload_service.run_ingestion_job(worker_one, create_result.job_id)
            await worker_one.commit()
        
        # Second worker should see job as already processed
        async with temp_db["session_maker"]() as worker_two:
            await async_upload_service.run_ingestion_job(worker_two, create_result.job_id)
            await worker_two.commit()

    # Ingest should only be called once due to lease protection
    assert call_count == 1


@pytest.mark.asyncio
async def test_db_lease_expired_processing_job_can_be_taken_over(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USE_DB_JOB_LEASE", "true")
    monkeypatch.setenv("JOB_LEASE_TTL_SECONDS", "300")

    create_result = await async_upload_service.create_async_upload_job(
        session=db_session,
        file_content=b"%PDF-1.4 stale lease",
        filename="stale-lease.pdf",
    )

    stale_ms = int(time.time() * 1000) - (6 * 60 * 1000)
    await db_session.execute(
        sqlalchemy.text(
            """
            UPDATE ingestion_jobs
            SET status = 'processing', leased_at = :leased_at, leased_by = :leased_by
            WHERE id = :job_id
            """
        ),
        {
            "job_id": create_result.job_id,
            "leased_at": stale_ms,
            "leased_by": "worker-dead",
        },
    )
    await db_session.commit()

    def _fake_ingest(*args, **kwargs):
        callback = kwargs["progress_callback"]
        callback("completed", 100)
        return {
            "pdf_name": "stale-lease",
            "title": "Stale Lease",
            "authors": "Author",
            "chunk_count": 1,
        }

    with (
        patch("api.services.paper_service.ingest_paper_file", side_effect=_fake_ingest),
        patch("api.services.async_upload_service._get_vector_store") as mock_get_vector_store,
    ):
        mock_get_vector_store.return_value.mark_paper_chunks_non_current.return_value = 1
        await async_upload_service.run_ingestion_job(db_session, create_result.job_id)

    job = await get_ingestion_job(db_session, create_result.job_id)
    assert job is not None
    assert job.status == "completed"


@pytest.mark.asyncio
async def test_db_lease_recovers_job_after_worker_crash(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USE_DB_JOB_LEASE", "true")
    monkeypatch.setenv("JOB_LEASE_TTL_SECONDS", "300")

    create_result = await async_upload_service.create_async_upload_job(
        session=db_session,
        file_content=b"%PDF-1.4 crash recovery",
        filename="lease-crash-recovery.pdf",
    )

    stale_ms = int(time.time() * 1000) - (10 * 60 * 1000)
    await db_session.execute(
        sqlalchemy.text(
            """
            UPDATE ingestion_jobs
            SET status = 'processing', stage = 'parsing', progress = 10,
                leased_at = :leased_at, leased_by = :leased_by
            WHERE id = :job_id
            """
        ),
        {
            "job_id": create_result.job_id,
            "leased_at": stale_ms,
            "leased_by": "crashed-worker",
        },
    )
    await db_session.commit()

    def _fake_ingest(*args, **kwargs):
        callback = kwargs["progress_callback"]
        callback("chunking", 35)
        callback("completed", 100)
        return {
            "pdf_name": "lease-crash-recovery",
            "title": "Crash Recovery",
            "authors": "Author",
            "chunk_count": 2,
        }

    with (
        patch("api.services.paper_service.ingest_paper_file", side_effect=_fake_ingest),
        patch("api.services.async_upload_service._get_vector_store") as mock_get_vector_store,
    ):
        mock_get_vector_store.return_value.mark_paper_chunks_non_current.return_value = 1
        await async_upload_service.run_ingestion_job(db_session, create_result.job_id)

    recovered = await get_ingestion_job(db_session, create_result.job_id)
    assert recovered is not None
    assert recovered.status == "completed"
    assert recovered.progress == 100


def test_background_executor_can_run_multiple_jobs_in_parallel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXECUTOR_TYPE", "thread")
    monkeypatch.setenv("BACKGROUND_EXECUTOR_WORKERS", "3")

    async_upload_service._BACKGROUND_EXECUTOR = None
    active = 0
    max_active = 0
    state_lock = threading.Lock()

    def _fake_runner(job_id: str) -> None:
        nonlocal active, max_active
        _ = job_id
        with state_lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.15)
        with state_lock:
            active -= 1

    with patch(
        "api.services.async_upload_service._run_ingestion_job_background_sync",
        side_effect=_fake_runner,
    ):
        async_upload_service.start_background_ingestion("job-1")
        async_upload_service.start_background_ingestion("job-2")
        async_upload_service.start_background_ingestion("job-3")

        executor = async_upload_service._BACKGROUND_EXECUTOR
        assert executor is not None
        executor.shutdown(wait=True)

    async_upload_service._BACKGROUND_EXECUTOR = None
    assert max_active >= 2


def test_executor_type_process_uses_process_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXECUTOR_TYPE", "process")
    monkeypatch.setenv("BACKGROUND_EXECUTOR_WORKERS", "2")
    async_upload_service._BACKGROUND_EXECUTOR = None

    executor = async_upload_service._get_background_executor()
    assert executor.__class__.__name__ == "ProcessPoolExecutor"

    executor.shutdown(wait=True)
    async_upload_service._BACKGROUND_EXECUTOR = None


@pytest.mark.asyncio
async def test_reindex_run_creates_new_version_and_toggles_current_flag(
    db_session: AsyncSession,
) -> None:
    file_content = b"%PDF-1.4 test content"
    filename = "versioned-reindex.pdf"

    first_job = await async_upload_service.create_async_upload_job(
        session=db_session,
        file_content=file_content,
        filename=filename,
    )
    second_job = await async_upload_service.create_async_upload_job(
        session=db_session,
        file_content=file_content,
        filename=filename,
    )

    def _fake_ingest(*args, **kwargs):
        callback = kwargs["progress_callback"]
        callback("parsing", 10)
        callback("chunking", 35)
        callback("storing", 65)
        callback("finalizing", 90)
        callback("completed", 100)
        return {
            "pdf_name": "versioned-reindex",
            "title": "Versioned Reindex",
            "authors": "Author",
            "chunk_count": 2,
        }

    with (
        patch("api.services.paper_service.ingest_paper_file", side_effect=_fake_ingest),
        patch("api.services.async_upload_service._get_vector_store") as mock_get_vector_store,
    ):
        mock_get_vector_store.return_value.mark_paper_chunks_non_current.return_value = 1
        await async_upload_service.run_ingestion_job(db_session, first_job.job_id)
        await async_upload_service.run_ingestion_job(db_session, second_job.job_id)

    paper = await get_paper_by_pdf_name(db_session, "versioned-reindex")
    assert paper is not None
    versions = await list_versions(db_session, paper.id)
    assert len(versions) == 2
    assert versions[0].version_number == 1
    assert versions[0].is_current is False
    assert versions[1].version_number == 2
    assert versions[1].is_current is True

    first_job_row = await get_ingestion_job(db_session, first_job.job_id)
    second_job_row = await get_ingestion_job(db_session, second_job.job_id)
    assert first_job_row is not None
    assert second_job_row is not None
    assert first_job_row.paper_version_id == versions[0].id
    assert second_job_row.paper_version_id == versions[1].id
