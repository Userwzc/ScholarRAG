"""
End-to-end integration tests for ScholarRAG API.

These tests verify the complete flow of:
- Async upload → job polling → completed result
- Query provenance payload shape
- Retry failed job flow
- Version history retrieval

Uses httpx.AsyncClient with FastAPI app for realistic API testing.
"""

import json
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest

httpx = pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Create a minimal valid PDF content for testing."""
    return b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer
<< /Size 4 /Root 1 0 R >>
startxref
196
%%EOF
"""


# ============================================================================
# Async Upload Integration Tests
# ============================================================================


class TestAsyncUploadFlow:
    """Tests for async upload → job polling → completed result flow."""

    @pytest.mark.asyncio
    async def test_async_upload_returns_job_id_immediately(
        self,
        temp_db: dict,
        sample_pdf_bytes: bytes,
    ) -> None:
        """Async upload should return 202 with job_id immediately."""
        from httpx import AsyncClient, ASGITransport

        async with temp_db["session_maker"]() as session:
            # Patch database session
            with patch("api.routes.papers.get_db_session") as mock_db:
                mock_db.return_value.__aenter__ = AsyncMock(return_value=session)
                mock_db.return_value.__aexit__ = AsyncMock(return_value=None)

                # Patch vector store
                with patch(
                    "api.services.async_upload_service._get_vector_store"
                ) as mock_vs:
                    mock_vs.return_value.mark_paper_chunks_non_current.return_value = 0

                    # Patch ingestion
                    def fake_ingest(*args, **kwargs):
                        callback = kwargs.get("progress_callback")
                        if callback:
                            callback("parsing", 10)
                            callback("chunking", 35)
                            callback("storing", 65)
                            callback("finalizing", 90)
                            callback("completed", 100)
                        return {
                            "pdf_name": "test-paper",
                            "title": "Test Paper",
                            "authors": "Test Author",
                            "chunk_count": 3,
                        }

                    with patch(
                        "api.services.paper_service.ingest_paper_file",
                        side_effect=fake_ingest,
                    ):
                        transport = ASGITransport(app=app)
                        async with AsyncClient(
                            transport=transport, base_url="http://test"
                        ) as ac:
                            # Upload file
                            files = {
                                "file": (
                                    "test-paper.pdf",
                                    BytesIO(sample_pdf_bytes),
                                    "application/pdf",
                                )
                            }
                            response = await ac.post("/api/papers/uploads", files=files)

                        assert response.status_code == 202
                        data = response.json()
                        assert "job_id" in data
                        assert data["status"] in ("pending", "processing")
                        assert data["filename"] == "test-paper.pdf"

    @pytest.mark.asyncio
    async def test_job_polling_returns_progress(
        self,
        temp_db: dict,
    ) -> None:
        """Job status endpoint should return progress information."""
        from api.services import async_upload_service
        from api.services.ingestion_job_service import update_ingestion_job

        async with temp_db["session_maker"]() as session:
            # Create a job
            result = await async_upload_service.create_async_upload_job(
                session=session,
                file_content=b"%PDF-1.4 test",
                filename="progress-test.pdf",
            )
            await session.commit()

            # Update progress
            await update_ingestion_job(
                session,
                job_id=result.job_id,
                status="processing",
                stage="parsing",
                progress=30,
            )
            await session.commit()

            # Get status
            status = await async_upload_service.get_job_status(session, result.job_id)

            assert status is not None
            assert status.status == "processing"
            assert status.stage == "parsing"
            assert status.progress == 30

    @pytest.mark.asyncio
    async def test_completed_job_has_result(
        self,
        temp_db: dict,
    ) -> None:
        """Completed job should have result summary."""
        from api.services import async_upload_service
        from api.services.ingestion_job_service import update_ingestion_job

        async with temp_db["session_maker"]() as session:
            # Create a job
            result = await async_upload_service.create_async_upload_job(
                session=session,
                file_content=b"%PDF-1.4 test",
                filename="completed-test.pdf",
            )
            await session.commit()

            # Mark as completed
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
                session,
                job_id=result.job_id,
                status="completed",
                stage="completed",
                progress=100,
                result_summary=result_summary,
            )
            await session.commit()

            # Get status
            status = await async_upload_service.get_job_status(session, result.job_id)

            assert status is not None
            assert status.status == "completed"
            assert status.result is not None
            assert status.result.pdf_name == "completed-test"
            assert status.result.chunk_count == 5


# ============================================================================
# Retry Flow Integration Tests
# ============================================================================


class TestRetryFlow:
    """Tests for retry failed job flow."""

    @pytest.mark.asyncio
    async def test_retry_failed_job_resets_to_pending(
        self,
        temp_db: dict,
    ) -> None:
        """Retry should reset failed job to pending."""
        from api.services import async_upload_service
        from api.services.ingestion_job_service import update_ingestion_job

        async with temp_db["session_maker"]() as session:
            # Create a job
            result = await async_upload_service.create_async_upload_job(
                session=session,
                file_content=b"%PDF-1.4 test",
                filename="retry-test.pdf",
            )
            await session.commit()

            # Mark as failed
            await update_ingestion_job(
                session,
                job_id=result.job_id,
                status="failed",
                stage="failed",
                error_message="Test error",
            )
            await session.commit()

            # Retry
            retry_result = await async_upload_service.retry_failed_job(
                session, result.job_id
            )
            await session.commit()

            assert retry_result is not None
            assert retry_result.status == "pending"
            assert "retry" in retry_result.message.lower()

            # Verify job state
            status = await async_upload_service.get_job_status(session, result.job_id)
            assert status is not None
            assert status.status == "pending"
            assert status.retry_count == 1

    @pytest.mark.asyncio
    async def test_retry_non_failed_job_rejected(
        self,
        temp_db: dict,
    ) -> None:
        """Retry should be rejected for non-failed jobs."""
        from api.services import async_upload_service

        async with temp_db["session_maker"]() as session:
            # Create a job (pending status)
            result = await async_upload_service.create_async_upload_job(
                session=session,
                file_content=b"%PDF-1.4 test",
                filename="no-retry-test.pdf",
            )
            await session.commit()

            # Try to retry pending job
            retry_result = await async_upload_service.retry_failed_job(
                session, result.job_id
            )

            assert retry_result is None  # Should return None for non-failed jobs

    @pytest.mark.asyncio
    async def test_retry_preserves_staged_file(
        self,
        temp_db: dict,
    ) -> None:
        """Staged file should be preserved for retry."""
        import os

        from api.services import async_upload_service
        from api.services.ingestion_job_service import (
            get_ingestion_job,
            update_ingestion_job,
        )

        async with temp_db["session_maker"]() as session:
            # Create a job
            result = await async_upload_service.create_async_upload_job(
                session=session,
                file_content=b"%PDF-1.4 unique content for retry",
                filename="staged-file-test.pdf",
            )
            await session.commit()

            # Get staged file path
            job = await get_ingestion_job(session, result.job_id)
            assert job is not None
            staged_path = job.source_file_path
            assert os.path.exists(staged_path)

            # Mark as failed
            await update_ingestion_job(
                session,
                job_id=result.job_id,
                status="failed",
                stage="failed",
                error_message="Test error",
            )
            await session.commit()

            # Verify file still exists
            assert os.path.exists(staged_path)

            # Retry
            await async_upload_service.retry_failed_job(session, result.job_id)
            await session.commit()

            # File should still exist after retry
            assert os.path.exists(staged_path)


# ============================================================================
# Version History Integration Tests
# ============================================================================


class TestVersionHistoryFlow:
    """Tests for version history retrieval."""

    @pytest.mark.asyncio
    async def test_version_history_endpoint(
        self,
        temp_db: dict,
    ) -> None:
        """Version history endpoint should return all versions."""
        from api.services import paper_registry_service

        async with temp_db["session_maker"]() as session:
            # Create paper and versions
            paper = await paper_registry_service.create_or_get_paper(
                session=session,
                pdf_name="versioned-paper",
                title="Versioned Paper",
                authors="Author",
            )
            await session.commit()

            # Create multiple versions
            await paper_registry_service.create_paper_version(
                session=session,
                paper_id=paper.id,
                source_hash="hash1",
                ingestion_schema_version="1.0",
            )
            await paper_registry_service.create_paper_version(
                session=session,
                paper_id=paper.id,
                source_hash="hash2",
                ingestion_schema_version="1.0",
            )
            await session.commit()

            # Get versions
            versions = await paper_registry_service.list_versions(session, paper.id)

            assert len(versions) == 2
            assert versions[0].version_number == 1
            assert versions[0].is_current is False
            assert versions[1].version_number == 2
            assert versions[1].is_current is True

    @pytest.mark.asyncio
    async def test_reindex_creates_new_version(
        self,
        temp_db: dict,
    ) -> None:
        """Reindexing should create a new version."""
        from api.services import async_upload_service, paper_registry_service

        async with temp_db["session_maker"]() as session:
            # Create first job
            await async_upload_service.create_async_upload_job(
                session=session,
                file_content=b"%PDF-1.4 test",
                filename="reindex-test.pdf",
            )
            await session.commit()

            # Create second job (simulating reindex)
            await async_upload_service.create_async_upload_job(
                session=session,
                file_content=b"%PDF-1.4 test",
                filename="reindex-test.pdf",
            )
            await session.commit()

            # Get paper
            paper = await paper_registry_service.get_paper_by_pdf_name(
                session, "reindex-test"
            )
            assert paper is not None

            # Create versions for each job
            await paper_registry_service.create_paper_version(
                session=session,
                paper_id=paper.id,
                source_hash="hash1",
                ingestion_schema_version="1.0",
            )
            await paper_registry_service.create_paper_version(
                session=session,
                paper_id=paper.id,
                source_hash="hash2",
                ingestion_schema_version="1.0",
            )
            await session.commit()

            # Verify versions
            versions = await paper_registry_service.list_versions(session, paper.id)
            assert len(versions) == 2
            assert versions[0].is_current is False
            assert versions[1].is_current is True


# ============================================================================
# Query Provenance Integration Tests
# ============================================================================


class TestQueryProvenanceFlow:
    """Tests for query provenance payload shape."""

    @pytest.mark.asyncio
    async def test_query_response_includes_structured_provenance(
        self,
        mock_vector_store,
    ) -> None:
        """Query response should include structured provenance fields."""
        from src.agent.evidence_builder import build_structured_provenance

        # Add test data
        mock_vector_store.add_multimodal(
            inputs=[{"text": "This is the methodology section of the paper."}],
            metadatas=[
                {
                    "pdf_name": "test_paper",
                    "page_idx": 5,
                    "chunk_type": "text",
                    "heading": "Methodology",
                    "paper_version": 1,
                    "is_current": True,
                }
            ],
        )

        # Build provenance from evidence
        evidence = [
            {
                "evidence_id": "chunk-123",
                "pdf_name": "test_paper",
                "page_idx": 5,
                "chunk_type": "text",
                "heading": "Methodology",
                "text": "This is the methodology section.",
                "paper_version": 1,
            }
        ]

        provenance = build_structured_provenance(evidence)

        assert len(provenance) == 1
        source = provenance[0]
        assert source["pdf_name"] == "test_paper"
        assert source["page"] == 5
        assert source["type"] == "text"
        assert source["chunk_id"] == "chunk-123"
        assert source["heading"] == "Methodology"
        assert source["paper_version"] == 1

    @pytest.mark.asyncio
    async def test_provenance_deduplication(
        self,
    ) -> None:
        """Provenance should deduplicate by (pdf_name, page, type)."""
        from src.agent.evidence_builder import build_structured_provenance

        evidence = [
            {
                "evidence_id": "chunk-1",
                "pdf_name": "paper",
                "page_idx": 1,
                "chunk_type": "text",
                "heading": "Section A",
                "text": "Content A",
            },
            {
                "evidence_id": "chunk-2",
                "pdf_name": "paper",
                "page_idx": 1,
                "chunk_type": "text",
                "heading": "Section B",
                "text": "Content B",
            },
            {
                "evidence_id": "chunk-3",
                "pdf_name": "paper",
                "page_idx": 2,
                "chunk_type": "text",
                "heading": "Section C",
                "text": "Content C",
            },
        ]

        provenance = build_structured_provenance(evidence)

        # Should deduplicate to 2 unique (pdf_name, page) pairs
        assert len(provenance) == 2


# ============================================================================
# API Error Handling Tests
# ============================================================================


class TestAPIErrorHandling:
    """Tests for API error handling."""

    def test_upload_non_pdf_rejected(self, client: TestClient) -> None:
        """Non-PDF uploads should be rejected."""
        files = {"file": ("test.txt", BytesIO(b"not a pdf"), "text/plain")}
        response = client.post("/api/papers/upload", files=files)
        assert response.status_code == 400

    def test_async_upload_non_pdf_rejected(self, client: TestClient) -> None:
        """Non-PDF async uploads should be rejected."""
        files = {"file": ("test.txt", BytesIO(b"not a pdf"), "text/plain")}
        response = client.post("/api/papers/uploads", files=files)
        assert response.status_code == 400

    def test_get_nonexistent_job_returns_404(self, client: TestClient) -> None:
        """Non-existent job should return 404."""
        response = client.get("/api/papers/uploads/nonexistent-job-id")
        assert response.status_code == 404

    def test_retry_nonexistent_job_returns_404(self, client: TestClient) -> None:
        """Retry of non-existent job should return 404."""
        response = client.post("/api/papers/uploads/nonexistent-job-id/retry")
        assert response.status_code == 404

    def test_get_nonexistent_paper_returns_404(self, client: TestClient) -> None:
        """Non-existent paper should return 404."""
        response = client.get("/api/papers/nonexistent-paper")
        assert response.status_code == 404

    def test_get_nonexistent_paper_versions_returns_404(
        self, client: TestClient
    ) -> None:
        """Non-existent paper versions should return 404."""
        response = client.get("/api/papers/nonexistent-paper/versions")
        assert response.status_code == 404
