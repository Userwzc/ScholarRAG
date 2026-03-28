"""
Regression tests for version-aware retrieval and current-version filtering.

These tests verify:
- Version-current flipping on reindex
- Retrieval filtering by current version
- Old version exclusion from default search
"""

from typing import Any
from unittest.mock import patch

import pytest

from api.services import paper_service
from src.core import ingestion


class _StubParser:
    """Stub parser for testing without MinerU dependency."""

    def __init__(self, output_dir: str, backend: str) -> None:
        self.output_dir = output_dir
        self.backend = backend

    @property
    def backend_subdir(self) -> str:
        return "auto"

    def parse_pdf(self, pdf_path: str) -> dict[str, Any]:
        return {
            "pdf_name": "versioned-paper",
            "title": "Versioned Paper",
        }

    def chunk_content(
        self, parsed_data: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return (
            [
                {
                    "content": "text chunk",
                    "type": "text",
                    "metadata": {
                        "page_idx": 0,
                        "heading": "Intro",
                    },
                }
            ],
            {
                "title_extracted": "Versioned Paper",
                "pre_abstract_meta": [],
                "footnotes_and_discarded": [],
                "references": [],
            },
        )


# ============================================================================
# Version Metadata Tests
# ============================================================================


class TestVersionMetadata:
    """Tests for version metadata in ingestion."""

    def test_process_paper_includes_version_metadata(self, monkeypatch) -> None:
        """process_paper should include paper_version and is_current in metadata."""
        monkeypatch.setattr(ingestion, "MinerUParser", _StubParser)

        _, metadata_list, _ = ingestion.process_paper(
            "/tmp/versioned-paper.pdf",
            save_markdown=False,
            paper_version=3,
            is_current=False,
        )

        assert metadata_list[0]["paper_version"] == 3
        assert metadata_list[0]["is_current"] is False

    def test_default_version_is_one(self, monkeypatch) -> None:
        """Default paper_version should be 1."""
        monkeypatch.setattr(ingestion, "MinerUParser", _StubParser)

        _, metadata_list, _ = ingestion.process_paper(
            "/tmp/versioned-paper.pdf",
            save_markdown=False,
        )

        assert metadata_list[0]["paper_version"] == 1
        assert metadata_list[0]["is_current"] is True


# ============================================================================
# Current Version Filtering Tests
# ============================================================================


class TestCurrentVersionFiltering:
    """Tests for current version filtering in retrieval."""

    def test_default_queries_only_return_current_version(
        self,
        mock_vector_store,
        mock_paper_service_vector_store,
    ) -> None:
        """Default queries should only return current version chunks."""
        _ = mock_paper_service_vector_store

        # Add chunks with different versions
        inputs = [
            {"text": "old version intro"},
            {"text": "current version intro"},
        ]
        metadatas = [
            {
                "pdf_name": "paper-a",
                "title": "Paper A",
                "authors": "Author",
                "chunk_type": "text",
                "heading": "Intro",
                "page_idx": 0,
                "paper_version": 1,
                "is_current": False,
            },
            {
                "pdf_name": "paper-a",
                "title": "Paper A",
                "authors": "Author",
                "chunk_type": "text",
                "heading": "Intro",
                "page_idx": 0,
                "paper_version": 2,
                "is_current": True,
            },
        ]
        mock_vector_store.add_multimodal(inputs, metadatas)

        # List papers should only show current version
        papers = paper_service.list_papers()
        assert len(papers) == 1
        assert papers[0].chunk_count == 1
        assert papers[0].paper_version == 2

        # Get paper detail should only show current version
        detail = paper_service.get_paper_detail("paper-a")
        assert detail is not None
        assert detail.chunk_count == 1
        assert detail.paper_version == 2
        assert detail.is_current is True

        # Get chunks should only return current version
        chunks = paper_service.get_paper_chunks("paper-a", page=1, limit=10)
        assert chunks.total == 1
        assert len(chunks.chunks) == 1
        assert chunks.chunks[0].paper_version == 2

    def test_version_override_returns_historical_chunks(
        self,
        mock_vector_store,
        mock_paper_service_vector_store,
    ) -> None:
        """Explicit version parameter should return historical chunks."""
        _ = mock_paper_service_vector_store

        mock_vector_store.add_multimodal(
            inputs=[
                {"text": "old version section"},
                {"text": "new version section"},
            ],
            metadatas=[
                {
                    "pdf_name": "paper-b",
                    "title": "Paper B",
                    "authors": "Author",
                    "chunk_type": "text",
                    "heading": "Old Intro",
                    "section_depth": 1,
                    "page_idx": 0,
                    "paper_version": 1,
                    "is_current": False,
                },
                {
                    "pdf_name": "paper-b",
                    "title": "Paper B",
                    "authors": "Author",
                    "chunk_type": "text",
                    "heading": "New Intro",
                    "section_depth": 1,
                    "page_idx": 0,
                    "paper_version": 2,
                    "is_current": True,
                },
            ],
        )

        # Request version 1 explicitly
        historical_chunks = paper_service.get_paper_chunks(
            "paper-b",
            page=1,
            limit=10,
            version=1,
        )
        assert historical_chunks.total == 1
        assert historical_chunks.chunks[0].paper_version == 1
        assert historical_chunks.chunks[0].is_current is False

        # TOC should also respect version
        historical_toc = paper_service.get_paper_toc("paper-b", version=1)
        assert historical_toc is not None
        assert len(historical_toc.items) == 1
        assert historical_toc.items[0].text == "Old Intro"

        # Current version TOC
        current_toc = paper_service.get_paper_toc("paper-b")
        assert current_toc is not None
        assert len(current_toc.items) == 1
        assert current_toc.items[0].text == "New Intro"


# ============================================================================
# Version Leak Detection Tests
# ============================================================================


class TestVersionLeakDetection:
    """Tests for detecting version leaks in retrieval results."""

    def test_no_version_leak_in_default_search(
        self,
        mock_vector_store,
        mock_paper_service_vector_store,
    ) -> None:
        """Default search should not leak non-current versions."""
        _ = mock_paper_service_vector_store

        # Add chunks with mixed versions
        mock_vector_store.add_multimodal(
            inputs=[
                {"text": "version 1 content"},
                {"text": "version 2 content"},
                {"text": "version 3 content"},
            ],
            metadatas=[
                {
                    "pdf_name": "paper-c",
                    "title": "Paper C",
                    "chunk_type": "text",
                    "page_idx": 0,
                    "paper_version": 1,
                    "is_current": False,
                },
                {
                    "pdf_name": "paper-c",
                    "title": "Paper C",
                    "chunk_type": "text",
                    "page_idx": 1,
                    "paper_version": 2,
                    "is_current": False,
                },
                {
                    "pdf_name": "paper-c",
                    "title": "Paper C",
                    "chunk_type": "text",
                    "page_idx": 2,
                    "paper_version": 3,
                    "is_current": True,
                },
            ],
        )

        # Search should only return version 3
        results = mock_vector_store.similarity_search("content", k=10)
        assert len(results) == 1
        assert results[0]["payload"]["metadata"]["paper_version"] == 3
        assert results[0]["payload"]["metadata"]["is_current"] is True

    def test_version_leak_check_function(self) -> None:
        """check_version_leak should detect non-current chunks."""
        from tests.evaluation.metrics import check_version_leak

        # No leak
        chunks_no_leak = [
            {"metadata": {"is_current": True}},
            {"metadata": {"is_current": None}},
            {"metadata": {}},
        ]
        assert check_version_leak(chunks_no_leak) is False

        # Leak detected
        chunks_with_leak = [
            {"metadata": {"is_current": True}},
            {"metadata": {"is_current": False}},
        ]
        assert check_version_leak(chunks_with_leak) is True


# ============================================================================
# Version Flipping Tests
# ============================================================================


class TestVersionFlipping:
    """Tests for version-current flipping on reindex."""

    @pytest.mark.asyncio
    async def test_reindex_creates_new_version_and_flips_current(
        self,
        temp_db,
    ) -> None:
        """Reindex should create new version and flip is_current flag."""
        from api.services import async_upload_service
        from api.services.paper_registry_service import (
            get_paper_by_pdf_name,
            list_versions,
        )

        async with temp_db["session_maker"]() as session:
            # Create first job
            result1 = await async_upload_service.create_async_upload_job(
                session=session,
                file_content=b"%PDF-1.4 test",
                filename="versioned-reindex.pdf",
            )
            await session.commit()

            # Create second job (simulating reindex)
            result2 = await async_upload_service.create_async_upload_job(
                session=session,
                file_content=b"%PDF-1.4 test",
                filename="versioned-reindex.pdf",
            )
            await session.commit()

            # Simulate ingestion for both jobs
            def fake_ingest(*args, **kwargs):
                callback = kwargs.get("progress_callback")
                if callback:
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
                patch(
                    "api.services.paper_service.ingest_paper_file",
                    side_effect=fake_ingest,
                ),
                patch("api.services.async_upload_service._get_vector_store") as mock_vs,
            ):
                mock_vs.return_value.mark_paper_chunks_non_current.return_value = 1
                await async_upload_service.run_ingestion_job(session, result1.job_id)
                await async_upload_service.run_ingestion_job(session, result2.job_id)
                await session.commit()

            # Verify versions
            paper = await get_paper_by_pdf_name(session, "versioned-reindex")
            assert paper is not None
            versions = await list_versions(session, paper.id)
            assert len(versions) == 2
            assert versions[0].version_number == 1
            assert versions[0].is_current is False
            assert versions[1].version_number == 2
            assert versions[1].is_current is True

    @pytest.mark.asyncio
    async def test_multiple_reindexes_create_sequential_versions(
        self,
        temp_db,
    ) -> None:
        """Multiple reindexes should create sequential version numbers."""
        from api.services import async_upload_service
        from api.services.paper_registry_service import (
            get_paper_by_pdf_name,
            list_versions,
        )

        async with temp_db["session_maker"]() as session:
            # Create multiple jobs for the same paper
            job_ids = []
            for i in range(3):
                result = await async_upload_service.create_async_upload_job(
                    session=session,
                    file_content=b"%PDF-1.4 test",
                    filename="multi-version.pdf",
                )
                job_ids.append(result.job_id)
                await session.commit()

            # Simulate ingestion for all jobs
            def fake_ingest(*args, **kwargs):
                callback = kwargs.get("progress_callback")
                if callback:
                    callback("completed", 100)
                return {
                    "pdf_name": "multi-version",
                    "title": "Multi Version",
                    "authors": "Author",
                    "chunk_count": 1,
                }

            with (
                patch(
                    "api.services.paper_service.ingest_paper_file",
                    side_effect=fake_ingest,
                ),
                patch("api.services.async_upload_service._get_vector_store") as mock_vs,
            ):
                mock_vs.return_value.mark_paper_chunks_non_current.return_value = 1
                for job_id in job_ids:
                    await async_upload_service.run_ingestion_job(session, job_id)
                    await session.commit()

            # Verify versions
            paper = await get_paper_by_pdf_name(session, "multi-version")
            assert paper is not None
            versions = await list_versions(session, paper.id)
            assert len(versions) == 3

            # Check version numbers and current flags
            for i, version in enumerate(versions):
                assert version.version_number == i + 1
                assert version.is_current == (i == len(versions) - 1)


# ============================================================================
# Version History Retrieval Tests
# ============================================================================


class TestVersionHistoryRetrieval:
    """Tests for version history retrieval."""

    @pytest.mark.asyncio
    async def test_version_history_lists_all_versions(
        self,
        temp_db,
    ) -> None:
        """Version history should list all versions for a paper."""
        from api.services import paper_registry_service

        async with temp_db["session_maker"]() as session:
            # Create paper and versions
            paper = await paper_registry_service.create_or_get_paper(
                session=session,
                pdf_name="history-test",
                title="History Test",
                authors="Author",
            )
            await session.commit()

            # Create multiple versions
            for i in range(3):
                await paper_registry_service.create_paper_version(
                    session=session,
                    paper_id=paper.id,
                    source_hash=f"hash-{i}",
                    ingestion_schema_version="1.0",
                )
                await session.commit()

            # Get version history
            versions = await paper_registry_service.list_versions(session, paper.id)
            assert len(versions) == 3

            # Verify version numbers
            for i, version in enumerate(versions):
                assert version.version_number == i + 1

    @pytest.mark.asyncio
    async def test_version_history_includes_metadata(
        self,
        temp_db,
    ) -> None:
        """Version history should include source_hash and schema_version."""
        from api.services import paper_registry_service

        async with temp_db["session_maker"]() as session:
            paper = await paper_registry_service.create_or_get_paper(
                session=session,
                pdf_name="metadata-test",
                title="Metadata Test",
                authors="Author",
            )
            await session.commit()

            await paper_registry_service.create_paper_version(
                session=session,
                paper_id=paper.id,
                source_hash="abc123",
                ingestion_schema_version=2,
            )
            await session.commit()

            versions = await paper_registry_service.list_versions(session, paper.id)
            assert len(versions) == 1
            assert versions[0].source_hash == "abc123"
            assert versions[0].ingestion_schema_version == 2
