"""
Regression tests for job state transitions, retry rules, and staged-file retention.

These tests verify:
- Job state transitions (pending → processing → completed/failed)
- Retry rules (only failed jobs can retry)
- Staged-file retention for retries
"""

import json
import os
from unittest.mock import patch

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")

from sqlalchemy.ext.asyncio import AsyncSession  # type: ignore[reportMissingImports]  # noqa: E402

from api.services import async_upload_service  # noqa: E402
from api.services.ingestion_job_service import (  # noqa: E402
    get_ingestion_job,
    update_ingestion_job,
)


# ============================================================================
# Job State Transition Tests
# ============================================================================


class TestJobStateTransitions:
    """Tests for job state transitions."""

    @pytest.mark.asyncio
    async def test_new_job_starts_as_pending(self, db_session: AsyncSession) -> None:
        """New job should start with status='pending' and stage='queued'."""
        result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test",
            filename="state-test.pdf",
        )

        assert result.status == "pending"

        job = await get_ingestion_job(db_session, result.job_id)
        assert job is not None
        assert job.status == "pending"
        assert job.stage == "queued"
        assert job.progress == 0

    @pytest.mark.asyncio
    async def test_job_transitions_to_processing(
        self, db_session: AsyncSession
    ) -> None:
        """Job should transition to processing when work begins."""
        result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test",
            filename="processing-test.pdf",
        )

        # Simulate processing start
        await update_ingestion_job(
            db_session,
            job_id=result.job_id,
            status="processing",
            stage="parsing",
            progress=10,
        )

        job = await get_ingestion_job(db_session, result.job_id)
        assert job is not None
        assert job.status == "processing"
        assert job.stage == "parsing"
        assert job.progress == 10

    @pytest.mark.asyncio
    async def test_job_transitions_to_completed(self, db_session: AsyncSession) -> None:
        """Job should transition to completed with result summary."""
        result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test",
            filename="completed-test.pdf",
        )

        # Simulate completion
        result_summary = json.dumps(
            {
                "pdf_name": "completed-test",
                "title": "Completed Test",
                "authors": "Author",
                "chunk_count": 5,
                "paper_version": 1,
            }
        )
        await update_ingestion_job(
            db_session,
            job_id=result.job_id,
            status="completed",
            stage="completed",
            progress=100,
            result_summary=result_summary,
        )

        job = await get_ingestion_job(db_session, result.job_id)
        assert job is not None
        assert job.status == "completed"
        assert job.stage == "completed"
        assert job.progress == 100
        assert job.result_summary is not None

    @pytest.mark.asyncio
    async def test_job_transitions_to_failed(self, db_session: AsyncSession) -> None:
        """Job should transition to failed with error message."""
        result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test",
            filename="failed-test.pdf",
        )

        # Simulate failure
        await update_ingestion_job(
            db_session,
            job_id=result.job_id,
            status="failed",
            stage="failed",
            error_message="Test error message",
        )

        job = await get_ingestion_job(db_session, result.job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.stage == "failed"
        assert job.error_message == "Test error message"

    @pytest.mark.asyncio
    async def test_job_progress_increases_monotonically(
        self, db_session: AsyncSession
    ) -> None:
        """Job progress should increase through stages."""
        result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test",
            filename="progress-test.pdf",
        )

        progress_values = []

        # Simulate progress updates
        for stage, progress in [
            ("parsing", 10),
            ("chunking", 35),
            ("storing", 65),
            ("finalizing", 90),
            ("completed", 100),
        ]:
            await update_ingestion_job(
                db_session,
                job_id=result.job_id,
                status="processing" if progress < 100 else "completed",
                stage=stage,
                progress=progress,
            )
            job = await get_ingestion_job(db_session, result.job_id)
            assert job is not None
            progress_values.append(job.progress)

        # Verify monotonic increase
        assert progress_values == sorted(progress_values)
        assert progress_values[-1] == 100


# ============================================================================
# Retry Rules Tests
# ============================================================================


class TestRetryRules:
    """Tests for retry rules."""

    @pytest.mark.asyncio
    async def test_only_failed_jobs_can_retry(self, db_session: AsyncSession) -> None:
        """Only failed jobs should be retryable."""
        # Create a pending job
        pending_result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test",
            filename="pending-retry-test.pdf",
        )

        # Try to retry pending job - should fail
        retry_result = await async_upload_service.retry_failed_job(
            db_session, pending_result.job_id
        )
        assert retry_result is None

        # Create a processing job
        processing_result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test",
            filename="processing-retry-test.pdf",
        )
        await update_ingestion_job(
            db_session,
            job_id=processing_result.job_id,
            status="processing",
            stage="parsing",
            progress=30,
        )

        # Try to retry processing job - should fail
        retry_result = await async_upload_service.retry_failed_job(
            db_session, processing_result.job_id
        )
        assert retry_result is None

        # Create a completed job
        completed_result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test",
            filename="completed-retry-test.pdf",
        )
        await update_ingestion_job(
            db_session,
            job_id=completed_result.job_id,
            status="completed",
            stage="completed",
            progress=100,
            result_summary=json.dumps({"pdf_name": "test", "chunk_count": 1}),
        )

        # Try to retry completed job - should fail
        retry_result = await async_upload_service.retry_failed_job(
            db_session, completed_result.job_id
        )
        assert retry_result is None

    @pytest.mark.asyncio
    async def test_failed_job_can_retry(self, db_session: AsyncSession) -> None:
        """Failed job should be retryable."""
        result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test",
            filename="failed-retry-test.pdf",
        )

        # Mark as failed
        await update_ingestion_job(
            db_session,
            job_id=result.job_id,
            status="failed",
            stage="failed",
            error_message="Test error",
        )

        # Retry should succeed
        retry_result = await async_upload_service.retry_failed_job(
            db_session, result.job_id
        )
        assert retry_result is not None
        assert retry_result.status == "pending"
        assert "retry" in retry_result.message.lower()

    @pytest.mark.asyncio
    async def test_retry_increments_retry_count(self, db_session: AsyncSession) -> None:
        """Each retry should increment retry_count."""
        result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test",
            filename="retry-count-test.pdf",
        )

        # Mark as failed and retry multiple times
        for i in range(3):
            await update_ingestion_job(
                db_session,
                job_id=result.job_id,
                status="failed",
                stage="failed",
                error_message=f"Error {i}",
            )
            await async_upload_service.retry_failed_job(db_session, result.job_id)

        job = await get_ingestion_job(db_session, result.job_id)
        assert job is not None
        assert job.retry_count == 3

    @pytest.mark.asyncio
    async def test_retry_resets_status_and_progress(
        self, db_session: AsyncSession
    ) -> None:
        """Retry should reset status to pending and progress to 0."""
        result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test",
            filename="reset-test.pdf",
        )

        # Simulate partial progress then failure
        await update_ingestion_job(
            db_session,
            job_id=result.job_id,
            status="processing",
            stage="storing",
            progress=65,
        )
        await update_ingestion_job(
            db_session,
            job_id=result.job_id,
            status="failed",
            stage="failed",
            error_message="Failed during storing",
        )

        # Retry
        await async_upload_service.retry_failed_job(db_session, result.job_id)

        job = await get_ingestion_job(db_session, result.job_id)
        assert job is not None
        assert job.status == "pending"
        assert job.stage == "queued"
        assert job.progress == 0
        assert job.error_message is None


# ============================================================================
# Staged File Retention Tests
# ============================================================================


class TestStagedFileRetention:
    """Tests for staged file retention."""

    @pytest.mark.asyncio
    async def test_staged_file_created_on_upload(
        self, db_session: AsyncSession
    ) -> None:
        """Staged file should be created when job is created."""
        file_content = b"%PDF-1.4 unique test content"
        result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=file_content,
            filename="staged-test.pdf",
        )

        job = await get_ingestion_job(db_session, result.job_id)
        assert job is not None
        assert os.path.exists(job.source_file_path)

        # Verify content
        with open(job.source_file_path, "rb") as f:
            saved_content = f.read()
        assert saved_content == file_content

    @pytest.mark.asyncio
    async def test_staged_file_retained_after_failure(
        self, db_session: AsyncSession
    ) -> None:
        """Staged file should be retained after job fails."""
        result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test content for failure",
            filename="retention-test.pdf",
        )

        job = await get_ingestion_job(db_session, result.job_id)
        assert job is not None
        staged_path = job.source_file_path

        # Mark as failed
        await update_ingestion_job(
            db_session,
            job_id=result.job_id,
            status="failed",
            stage="failed",
            error_message="Test failure",
        )

        # File should still exist
        assert os.path.exists(staged_path)

    @pytest.mark.asyncio
    async def test_staged_file_retained_after_retry(
        self, db_session: AsyncSession
    ) -> None:
        """Staged file should be retained after retry."""
        result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test content for retry",
            filename="retry-retention-test.pdf",
        )

        job = await get_ingestion_job(db_session, result.job_id)
        assert job is not None
        staged_path = job.source_file_path

        # Mark as failed
        await update_ingestion_job(
            db_session,
            job_id=result.job_id,
            status="failed",
            stage="failed",
            error_message="Test failure",
        )

        # Retry
        await async_upload_service.retry_failed_job(db_session, result.job_id)

        # File should still exist
        assert os.path.exists(staged_path)

    @pytest.mark.asyncio
    async def test_staged_file_cleaned_up_after_success(
        self, db_session: AsyncSession
    ) -> None:
        """Staged file should be cleaned up after successful completion."""
        result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test content for cleanup",
            filename="cleanup-test.pdf",
        )

        job = await get_ingestion_job(db_session, result.job_id)
        assert job is not None
        staged_path = job.source_file_path
        job_dir = os.path.dirname(staged_path)

        # Verify file exists
        assert os.path.exists(staged_path)

        # Simulate successful completion with cleanup
        async_upload_service.cleanup_staged_file(result.job_id)

        # Directory should be removed
        assert not os.path.exists(job_dir)

    @pytest.mark.asyncio
    async def test_staged_file_available_for_multiple_retries(
        self, db_session: AsyncSession
    ) -> None:
        """Staged file should be available for multiple retry attempts."""
        result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test content for multiple retries",
            filename="multi-retry-test.pdf",
        )

        job = await get_ingestion_job(db_session, result.job_id)
        assert job is not None
        staged_path = job.source_file_path

        # Fail and retry multiple times
        for i in range(3):
            await update_ingestion_job(
                db_session,
                job_id=result.job_id,
                status="failed",
                stage="failed",
                error_message=f"Failure {i}",
            )
            await async_upload_service.retry_failed_job(db_session, result.job_id)

            # File should still exist after each retry
            assert os.path.exists(staged_path), f"File missing after retry {i}"


# ============================================================================
# Duplicate Execution Prevention Tests
# ============================================================================


class TestDuplicateExecutionPrevention:
    """Tests for preventing duplicate job execution."""

    @pytest.mark.asyncio
    async def test_processing_job_cannot_be_restarted(
        self, db_session: AsyncSession
    ) -> None:
        """Processing job should not be restartable."""
        result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test",
            filename="no-restart-test.pdf",
        )

        # Mark as processing
        await update_ingestion_job(
            db_session,
            job_id=result.job_id,
            status="processing",
            stage="parsing",
            progress=20,
        )

        # Try to run ingestion again - should be a no-op
        with patch("api.services.paper_service.ingest_paper_file") as mock_ingest:
            mock_ingest.return_value = {
                "pdf_name": "no-restart-test",
                "title": "Test",
                "authors": "Author",
                "chunk_count": 1,
            }
            with patch(
                "api.services.async_upload_service._get_vector_store"
            ) as mock_vs:
                mock_vs.return_value.mark_paper_chunks_non_current.return_value = 0
                await async_upload_service.run_ingestion_job(db_session, result.job_id)

        # Ingest should not have been called
        mock_ingest.assert_not_called()

    @pytest.mark.asyncio
    async def test_completed_job_cannot_be_restarted(
        self, db_session: AsyncSession
    ) -> None:
        """Completed job should not be restartable."""
        result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test",
            filename="completed-no-restart-test.pdf",
        )

        # Mark as completed
        await update_ingestion_job(
            db_session,
            job_id=result.job_id,
            status="completed",
            stage="completed",
            progress=100,
            result_summary=json.dumps({"pdf_name": "test", "chunk_count": 1}),
        )

        # Try to run ingestion again - should be a no-op
        with patch("api.services.paper_service.ingest_paper_file") as mock_ingest:
            mock_ingest.return_value = {
                "pdf_name": "test",
                "title": "Test",
                "authors": "Author",
                "chunk_count": 1,
            }
            with patch(
                "api.services.async_upload_service._get_vector_store"
            ) as mock_vs:
                mock_vs.return_value.mark_paper_chunks_non_current.return_value = 0
                await async_upload_service.run_ingestion_job(db_session, result.job_id)

        # Ingest should not have been called
        mock_ingest.assert_not_called()


# ============================================================================
# Error Message Sanitization Tests
# ============================================================================


class TestErrorMessageSanitization:
    """Tests for error message sanitization."""

    @pytest.mark.asyncio
    async def test_long_error_message_truncated(self, db_session: AsyncSession) -> None:
        """Long error messages should be truncated."""
        result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test",
            filename="long-error-test.pdf",
        )

        # Simulate failure with very long error
        long_error = "x" * 1000
        with (
            patch(
                "api.services.paper_service.ingest_paper_file",
                side_effect=RuntimeError(long_error),
            ),
            patch("api.services.async_upload_service._get_vector_store") as mock_vs,
        ):
            mock_vs.return_value.mark_paper_chunks_non_current.return_value = 0
            await async_upload_service.run_ingestion_job(db_session, result.job_id)

        job = await get_ingestion_job(db_session, result.job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.error_message is not None
        assert len(job.error_message) <= 500

    @pytest.mark.asyncio
    async def test_whitespace_normalized_in_error(
        self, db_session: AsyncSession
    ) -> None:
        """Whitespace in error messages should be normalized."""
        result = await async_upload_service.create_async_upload_job(
            session=db_session,
            file_content=b"%PDF-1.4 test",
            filename="whitespace-error-test.pdf",
        )

        # Simulate failure with messy whitespace
        messy_error = "Error   with   lots   of   whitespace\n\nand\nnewlines"
        with (
            patch(
                "api.services.paper_service.ingest_paper_file",
                side_effect=RuntimeError(messy_error),
            ),
            patch("api.services.async_upload_service._get_vector_store") as mock_vs,
        ):
            mock_vs.return_value.mark_paper_chunks_non_current.return_value = 0
            await async_upload_service.run_ingestion_job(db_session, result.job_id)

        job = await get_ingestion_job(db_session, result.job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.error_message is not None
        # Should have normalized whitespace
        assert "  " not in job.error_message
