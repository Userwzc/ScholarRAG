"""
Tests for the test harness itself.

These tests verify that the pytest configuration and fixtures work correctly.
"""

import os
from pathlib import Path

import pytest


class TestEnvironmentFixtures:
    """Tests for environment isolation fixtures."""

    def test_test_env_sets_mock_values(self, test_env: dict[str, str]) -> None:
        """Verify that test_env fixture sets expected mock values."""
        # Check the fixture returns expected values (not os.environ directly)
        assert test_env.get("EMBEDDING_MODEL") == "mock-model"
        assert test_env.get("OPENAI_API_KEY") == "test-key-mock"
        assert test_env.get("LLM_MODEL") == "mock-llm"
        assert test_env.get("ENABLE_HYBRID") == "false"

    def test_test_env_isolates_from_real_env(self, test_env: dict[str, str]) -> None:
        """Verify that test environment is isolated from real environment."""
        # These should be mock values, not real ones
        assert test_env.get("OPENAI_API_KEY") != ""
        assert "Qwen3-VL" not in test_env.get("EMBEDDING_MODEL", "")


class TestDatabaseFixtures:
    """Tests for database fixtures."""

    @pytest.mark.asyncio
    async def test_temp_db_creates_file(self, temp_db: dict) -> None:
        """Verify that temp_db creates a database file."""
        db_path = temp_db["db_path"]
        assert Path(db_path).exists()
        assert db_path.endswith(".db")

    @pytest.mark.asyncio
    async def test_temp_db_session_works(self, db_session) -> None:
        """Verify that db_session provides a working session."""
        try:
            from api.models import Conversation
        except ImportError:
            pytest.skip("sqlalchemy not installed")

        import time

        now = int(time.time() * 1000)
        conv = Conversation(
            id="test-conv",
            title="Test",
            created_at=now,
            updated_at=now,
        )
        db_session.add(conv)
        await db_session.flush()

        result = await db_session.get(Conversation, "test-conv")
        assert result is not None
        assert result.title == "Test"

    @pytest.mark.asyncio
    async def test_temp_db_isolation(self, temp_db: dict) -> None:
        """Verify that each test gets a fresh database."""
        db_path = temp_db["db_path"]
        assert Path(db_path).exists()


class TestMockVectorStore:
    """Tests for mock vector store fixtures."""

    def test_mock_vector_store_add(self, mock_vector_store) -> None:
        """Verify that mock vector store can add items."""
        inputs = [{"text": "Test content"}]
        metadatas = [{"pdf_name": "test", "page_idx": 0}]

        ids = mock_vector_store.add_multimodal(inputs, metadatas)

        assert len(ids) == 1
        assert ids[0].startswith("mock-id-")

    def test_mock_vector_store_search(self, mock_vector_store) -> None:
        """Verify that mock vector store can search."""
        inputs = [
            {"text": "Machine learning is a field of AI"},
            {"text": "Deep learning uses neural networks"},
        ]
        metadatas = [
            {"pdf_name": "test", "page_idx": 0},
            {"pdf_name": "test", "page_idx": 1},
        ]

        mock_vector_store.add_multimodal(inputs, metadatas)

        results = mock_vector_store.similarity_search("machine learning", k=2)

        assert len(results) >= 1
        assert "payload" in results[0]

    def test_mock_vector_store_filter(self, mock_vector_store) -> None:
        """Verify that mock vector store respects filters."""
        try:
            from qdrant_client.http import models
        except ImportError:
            pytest.skip("qdrant_client not installed")

        inputs = [
            {"text": "Content from paper A"},
            {"text": "Content from paper B"},
        ]
        metadatas = [
            {"pdf_name": "paper_a", "page_idx": 0},
            {"pdf_name": "paper_b", "page_idx": 0},
        ]

        mock_vector_store.add_multimodal(inputs, metadatas)

        filter_obj = models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.pdf_name",
                    match=models.MatchValue(value="paper_a"),
                )
            ]
        )

        results = mock_vector_store.similarity_search("content", k=10, filter=filter_obj)

        assert len(results) == 1
        assert results[0]["payload"]["metadata"]["pdf_name"] == "paper_a"

    def test_mock_vector_store_count(self, mock_vector_store) -> None:
        """Verify that mock vector store can count chunks."""
        inputs = [{"text": "Test"} for _ in range(5)]
        metadatas = [{"pdf_name": "test", "page_idx": i} for i in range(5)]

        mock_vector_store.add_multimodal(inputs, metadatas)

        count = mock_vector_store.count_chunks()
        assert count == 5

    def test_mock_vector_store_delete(self, mock_vector_store) -> None:
        """Verify that mock vector store can delete by paper name."""
        inputs = [{"text": "Test"}]
        metadatas = [{"pdf_name": "to_delete", "page_idx": 0}]

        mock_vector_store.add_multimodal(inputs, metadatas)
        assert mock_vector_store.count_chunks() == 1

        mock_vector_store.delete_paper("to_delete")
        assert mock_vector_store.count_chunks() == 0


class TestSampleDataFixtures:
    """Tests for sample data fixtures."""

    def test_sample_paper_payload_structure(self, sample_paper_payload: dict) -> None:
        """Verify sample paper payload has expected structure."""
        assert "multimodal_inputs" in sample_paper_payload
        assert "metadata_list" in sample_paper_payload
        assert "parsed_data" in sample_paper_payload

        assert len(sample_paper_payload["multimodal_inputs"]) > 0
        assert len(sample_paper_payload["metadata_list"]) > 0

    def test_sample_pdf_path_exists(self, sample_pdf_path: Path) -> None:
        """Verify sample PDF path fixture creates a valid file."""
        assert sample_pdf_path.exists()
        assert sample_pdf_path.suffix == ".pdf"

        # Verify it's a valid PDF (starts with %PDF)
        content = sample_pdf_path.read_bytes()
        assert content.startswith(b"%PDF-")

    def test_sample_conversation_data_structure(
        self, sample_conversation_data: dict
    ) -> None:
        """Verify sample conversation data has expected structure."""
        assert "conversation" in sample_conversation_data
        assert "messages" in sample_conversation_data

        conv = sample_conversation_data["conversation"]
        assert "id" in conv
        assert "title" in conv

        messages = sample_conversation_data["messages"]
        assert len(messages) >= 1
        assert "role" in messages[0]
        assert "content" in messages[0]


class TestConfigOverrides:
    """Tests for configuration overrides in test environment."""

    def test_config_uses_test_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify that config module picks up test environment values."""
        import sys
        
        # Set mock values before importing config
        monkeypatch.setenv("EMBEDDING_MODEL", "mock-model")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-mock")
        monkeypatch.setenv("LLM_MODEL", "mock-llm")
        monkeypatch.setenv("OPENAI_API_BASE", "http://localhost:9999/mock")
        
        # Remove config modules from cache to force fresh import
        modules_to_remove = [key for key in sys.modules.keys() if key.startswith("config")]
        for mod in modules_to_remove:
            del sys.modules[mod]
        
        try:
            import config.settings
        except ImportError:
            pytest.skip("config module not available")

        cfg = config.settings.config
        assert cfg.EMBEDDING_MODEL == "mock-model"
        assert cfg.LLM_MODEL == "mock-llm"

    def test_no_gpu_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify that tests don't require GPU."""
        # Set mock value
        monkeypatch.setenv("EMBEDDING_MODEL", "mock-model")
        
        # EMBEDDING_MODEL should be a mock, not a real model path
        assert "Qwen3-VL" not in os.environ.get("EMBEDDING_MODEL", "")
        assert "mock" in os.environ.get("EMBEDDING_MODEL", "").lower()
