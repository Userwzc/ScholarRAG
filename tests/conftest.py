"""
Pytest configuration and shared fixtures for ScholarRAG tests.

This module provides deterministic test fixtures that allow running tests
without GPU, Qdrant, or external API dependencies.

## Running Tests

### Local Development
```bash
# Run all unit tests (no external dependencies)
pytest tests -q -k "not integration"

# Run all tests including integration (requires Qdrant/GPU)
pytest tests -q

# Run specific test file
pytest tests/unit/test_paper_service.py -v
```

### CI Environment
```bash
# CI runs unit tests only by default
pytest tests -q -k "not integration"

# With explicit env isolation
env -u OPENAI_API_KEY -u EMBEDDING_MODEL pytest tests -q -k "not integration"
```

## Test Categories
- `@pytest.mark.unit`: Fast, no external dependencies
- `@pytest.mark.integration`: Requires Qdrant/GPU/external APIs
- `@pytest.mark.slow`: Long-running tests

## Fixtures Overview
- `test_env`: Isolated environment variables for testing
- `temp_db`: Temporary SQLite database with async session
- `mock_vector_store`: Fake vector store for deterministic testing
- `sample_paper_payload`: Representative parsed paper data
- `sample_pdf_path`: Path to a minimal test PDF
"""

import os
import sys
import tempfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure project root is in path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ============================================================================
# Environment Fixtures
# ============================================================================


@pytest.fixture(scope="session", autouse=True)
def test_env() -> Generator[dict[str, str], None, None]:
    """
    Set up isolated test environment variables.

    This fixture runs automatically for all tests and ensures:
    - No real GPU/model dependencies
    - No external API calls
    - Deterministic configuration

    Tests can override these by setting env vars before importing config.
    """
    # Store original values
    original_env: dict[str, str | None] = {}
    test_env_vars = {
        # Disable GPU/model dependencies
        "EMBEDDING_MODEL": "mock-model",
        # Disable external APIs
        "OPENAI_API_KEY": "test-key-mock",
        "OPENAI_API_BASE": "http://localhost:9999/mock",
        "LLM_MODEL": "mock-llm",
        # Use in-memory Qdrant mock
        "QDRANT_HOST": "localhost",
        "QDRANT_PORT": "6333",
        "QDRANT_COLLECTION_NAME": "test_collection",
        # Test-specific settings
        "RAG_TOP_K": "5",
        "SCORE_THRESHOLD": "0.3",
        "AGENT_MAX_ITERATIONS": "5",
        "ENABLE_HYBRID": "false",
        "MINERU_BACKEND": "pipeline",
        "MINERU_MODEL_SOURCE": "local",
        # PDF storage
        "PDF_STORAGE_DIR": "/tmp/scholarrag_test_pdfs",
        # Database
        "DATABASE_PATH": "",  # Will be set by temp_db fixture
    }

    # Save original values and set test values
    for key, value in test_env_vars.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    yield test_env_vars

    # Restore original values
    for key, original_value in original_env.items():
        if original_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original_value


# ============================================================================
# Database Fixtures
# ============================================================================


@pytest.fixture
async def temp_db() -> AsyncGenerator[dict[str, Any], None]:
    """
    Create a temporary SQLite database for testing.

    Returns a dict with:
        - `db_path`: Path to the temporary database file
        - `session`: AsyncSession for database operations

    Usage:
        async for db in temp_db():
            async with db["session"] as session:
                # Use session for DB operations
                pass
    """
    # Check if sqlalchemy is available
    try:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    except ImportError:
        pytest.skip("sqlalchemy not installed")
        return

    # Check if aiosqlite is available
    try:
        import aiosqlite  # noqa: F401
    except ImportError:
        pytest.skip("aiosqlite not installed")
        return

    from api.database import Base

    # Create temp file for database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Set database path in environment
    os.environ["DATABASE_PATH"] = db_path

    # Create async engine with temp database
    database_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(database_url, echo=False)
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield {
        "db_path": db_path,
        "engine": engine,
        "session_maker": async_session_maker,
    }

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

    # Remove temp file
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
async def db_session(temp_db: dict[str, Any]) -> AsyncGenerator[Any, None]:
    """
    Provide an async database session for tests.

    This is a convenience fixture that wraps temp_db and provides
    a ready-to-use session with automatic commit/rollback.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    async with temp_db["session_maker"]() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ============================================================================
# Vector Store Mock Fixtures
# ============================================================================


class MockVectorStore:
    """
    Mock vector store for deterministic testing.

    Provides a minimal implementation that mimics MultimodalQdrantStore
    without requiring Qdrant, GPU, or model dependencies.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._id_counter = 0

    def add_multimodal(
        self,
        inputs: list[dict[str, Any]],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
        **kwargs,
    ) -> list[str]:
        """Store multimodal inputs with deterministic IDs."""
        metadatas = metadatas or [{} for _ in inputs]
        if ids is None:
            ids = [f"mock-id-{self._id_counter + i}" for i in range(len(inputs))]
            self._id_counter += len(inputs)

        for inp, meta, pid in zip(inputs, metadatas, ids):
            text = inp.get("text", "") if isinstance(inp, dict) else str(inp)
            self._store[pid] = {
                "id": pid,
                "payload": {
                    "page_content": text,
                    "metadata": meta,
                    "_multimodal_input": inp,
                },
            }

        return ids

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter: Any = None,
        score_threshold: float = 0.0,
        current_only: bool = True,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """
        Mock similarity search.

        Returns results that match the filter criteria (if provided)
        or all stored items up to k.
        """
        results = []

        for pid, item in self._store.items():
            payload = item["payload"]
            meta = payload.get("metadata", {})

            if current_only and meta.get("is_current") is False:
                continue

            # Apply filter if provided
            if filter is not None:
                if not self._matches_filter(meta, filter):
                    continue

            # Simple text matching for mock scoring
            text = payload.get("page_content", "")
            query_lower = query.lower()
            text_lower = text.lower()

            # Calculate mock score based on word overlap
            query_words = set(query_lower.split())
            text_words = set(text_lower.split())
            overlap = len(query_words & text_words)
            score = min(1.0, overlap / max(len(query_words), 1))

            if score >= score_threshold:
                results.append({"score": score, "payload": payload})

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:k]

    def _matches_filter(self, metadata: dict[str, Any], filter_obj: Any) -> bool:
        """Check if metadata matches a Qdrant filter object."""
        # Handle Filter objects with must conditions
        if hasattr(filter_obj, "must") and filter_obj.must:
            for condition in filter_obj.must:
                if not self._matches_condition(metadata, condition):
                    return False
            return True
        return True

    def _matches_condition(self, metadata: dict[str, Any], condition: Any) -> bool:
        """Check if metadata matches a single condition."""
        if hasattr(condition, "key") and hasattr(condition, "match"):
            key = condition.key
            # Handle nested keys like "metadata.pdf_name"
            if key.startswith("metadata."):
                key = key[9:]  # Remove "metadata." prefix

            match_value = condition.match.value if hasattr(condition.match, "value") else None
            return metadata.get(key) == match_value
        return True

    def get_all_papers(
        self,
        filter: Any = None,
        current_only: bool = True,
    ) -> list[dict[str, Any]]:
        results = []
        for item in self._store.values():
            payload = item["payload"]
            meta = payload.get("metadata", {})
            if current_only and meta.get("is_current") is False:
                continue
            if filter is not None and not self._matches_filter(meta, filter):
                continue
            results.append({"payload": payload})
        return results

    def scroll_chunks(
        self,
        filter: Any = None,
        limit: int = 10000,
        offset: Any = None,
        current_only: bool = True,
    ) -> tuple[list[dict[str, Any]], Any]:
        """Paginate through stored chunks."""
        results = []
        for pid, item in self._store.items():
            payload = item["payload"]
            meta = payload.get("metadata", {})

            if current_only and meta.get("is_current") is False:
                continue

            if filter is not None and not self._matches_filter(meta, filter):
                continue

            results.append({"id": pid, "payload": payload})

        return results[:limit], None

    def count_chunks(self, filter: Any = None, current_only: bool = True) -> int:
        """Count chunks matching filter."""
        count = 0
        for item in self._store.values():
            meta = item["payload"].get("metadata", {})
            if current_only and meta.get("is_current") is False:
                continue
            if filter is None or self._matches_filter(meta, filter):
                count += 1
        return count

    def mark_paper_chunks_non_current(
        self,
        pdf_name: str,
        keep_version: int,
        batch_size: int = 256,
    ) -> int:
        _ = batch_size
        updated = 0
        for item in self._store.values():
            payload = item.get("payload", {})
            meta = payload.get("metadata", {})
            if meta.get("pdf_name") != pdf_name:
                continue
            if meta.get("paper_version") == keep_version:
                continue
            if meta.get("is_current") is False:
                continue
            meta["is_current"] = False
            updated += 1
        return updated

    def delete_by_metadata(self, filter: Any) -> bool:
        """Delete items matching filter."""
        to_delete = []
        for pid, item in self._store.items():
            meta = item["payload"].get("metadata", {})
            if self._matches_filter(meta, filter):
                to_delete.append(pid)

        for pid in to_delete:
            del self._store[pid]

        return True

    def delete_paper(self, pdf_name: str) -> bool:
        """Delete all chunks for a paper."""
        # Simple implementation without qdrant_client dependency
        to_delete = []
        for pid, item in self._store.items():
            meta = item["payload"].get("metadata", {})
            if meta.get("pdf_name") == pdf_name:
                to_delete.append(pid)

        for pid in to_delete:
            del self._store[pid]

        return True

    def fetch_by_metadata(
        self,
        filter: Any,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Fetch items by metadata filter."""
        results = []
        for item in self._store.values():
            meta = item["payload"].get("metadata", {})
            if self._matches_filter(meta, filter):
                results.append({"payload": item["payload"]})
                if len(results) >= limit:
                    break
        return results


@pytest.fixture
def mock_vector_store() -> MockVectorStore:
    """
    Provide a mock vector store for testing.

    This fixture returns a MockVectorStore instance that can be used
    to test vector store interactions without real Qdrant/GPU dependencies.
    """
    return MockVectorStore()


@pytest.fixture
def mock_get_vector_store(mock_vector_store: MockVectorStore) -> Generator[MagicMock, None, None]:
    """
    Mock the get_vector_store function to return a mock vector store.

    Usage:
        def test_something(mock_get_vector_store):
            # get_vector_store() will return mock_vector_store
            from src.rag.vector_store import get_vector_store
            store = get_vector_store()
            store.add_multimodal([...], [...])
    """
    with patch("src.rag.vector_store.get_vector_store") as mock:
        mock.return_value = mock_vector_store
        yield mock


@pytest.fixture
def mock_paper_service_vector_store(mock_vector_store: MockVectorStore) -> Generator[MagicMock, None, None]:
    """
    Mock vector store for paper_service module.

    This patches the _get_vector_store function in paper_service.
    """
    with patch("api.services.paper_service._get_vector_store") as mock:
        mock.return_value = mock_vector_store
        yield mock


# ============================================================================
# Sample Data Fixtures
# ============================================================================


@pytest.fixture
def sample_paper_payload() -> dict[str, Any]:
    """
    Provide a representative parsed paper payload for testing.

    Returns a dict containing:
        - multimodal_inputs: List of text/image inputs
        - metadata_list: List of metadata dicts
        - parsed_data: Summary data from parsing
    """
    return {
        "multimodal_inputs": [
            {"text": "Abstract: This paper presents a novel approach to machine learning."},
            {"text": "1. Introduction\nMachine learning has become a fundamental tool..."},
            {"text": "2. Methodology\nWe propose a new framework for..."},
            {"text": "Figure 1: Architecture diagram of the proposed model.", "image": "/tmp/test_image.png"},
            {"text": "3. Results\nOur experiments show significant improvements..."},
            {"text": "Table 1: Comparison of accuracy metrics across methods."},
        ],
        "metadata_list": [
            {
                "pdf_name": "test_paper",
                "title": "A Novel Approach to Machine Learning",
                "authors": "John Doe, Jane Smith",
                "page_idx": 0,
                "chunk_type": "text",
                "heading": "Abstract",
            },
            {
                "pdf_name": "test_paper",
                "title": "A Novel Approach to Machine Learning",
                "authors": "John Doe, Jane Smith",
                "page_idx": 1,
                "chunk_type": "text",
                "heading": "1. Introduction",
            },
            {
                "pdf_name": "test_paper",
                "title": "A Novel Approach to Machine Learning",
                "authors": "John Doe, Jane Smith",
                "page_idx": 2,
                "chunk_type": "text",
                "heading": "2. Methodology",
            },
            {
                "pdf_name": "test_paper",
                "title": "A Novel Approach to Machine Learning",
                "authors": "John Doe, Jane Smith",
                "page_idx": 2,
                "chunk_type": "image",
                "heading": "Figure 1",
                "img_path": "images/fig1.png",
            },
            {
                "pdf_name": "test_paper",
                "title": "A Novel Approach to Machine Learning",
                "authors": "John Doe, Jane Smith",
                "page_idx": 3,
                "chunk_type": "text",
                "heading": "3. Results",
            },
            {
                "pdf_name": "test_paper",
                "title": "A Novel Approach to Machine Learning",
                "authors": "John Doe, Jane Smith",
                "page_idx": 3,
                "chunk_type": "table",
                "heading": "Table 1",
            },
        ],
        "parsed_data": {
            "pdf_name": "test_paper",
            "title": "A Novel Approach to Machine Learning",
            "authors": "John Doe, Jane Smith",
            "total_pages": 4,
            "total_chunks": 6,
        },
    }


@pytest.fixture
def sample_pdf_path(tmp_path: Path) -> Path:
    """
    Create a minimal test PDF file.

    Returns the path to a minimal valid PDF that can be used
    for testing upload/processing workflows.
    """
    # Create a minimal valid PDF content
    # This is a valid PDF with one blank page
    pdf_content = b"""%PDF-1.4
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
    pdf_path = tmp_path / "test_paper.pdf"
    pdf_path.write_bytes(pdf_content)
    return pdf_path


@pytest.fixture
def sample_conversation_data() -> dict[str, Any]:
    """
    Provide sample conversation data for testing.

    Returns a dict with conversation and message data.
    """
    import time

    now = int(time.time() * 1000)
    return {
        "conversation": {
            "id": "test-conv-1",
            "title": "Test Conversation",
            "created_at": now,
            "updated_at": now,
        },
        "messages": [
            {
                "id": "msg-1",
                "conversation_id": "test-conv-1",
                "role": "user",
                "content": "What is the main contribution of this paper?",
                "created_at": now,
            },
            {
                "id": "msg-2",
                "conversation_id": "test-conv-1",
                "role": "assistant",
                "content": "The main contribution is a novel approach to machine learning.",
                "steps": [{"type": "search", "tool": "retrieve", "count": 3}],
                "sources": [{"pdf_name": "test_paper", "page": 1, "type": "text"}],
                "created_at": now + 1000,
            },
        ],
    }


# ============================================================================
# API Test Fixtures
# ============================================================================


@pytest.fixture
def mock_process_paper(sample_paper_payload: dict[str, Any]) -> Generator[MagicMock, None, None]:
    """
    Mock the process_paper function for testing upload workflows.
    """
    with patch("src.core.ingestion.process_paper") as mock:
        mock.return_value = (
            sample_paper_payload["multimodal_inputs"],
            sample_paper_payload["metadata_list"],
            sample_paper_payload["parsed_data"],
        )
        yield mock


@pytest.fixture
def mock_paper_manager() -> Generator[MagicMock, None, None]:
    """
    Mock the PaperManager for testing delete workflows.
    """
    with patch("api.services.paper_service.PaperManager") as mock:
        mock_instance = MagicMock()
        mock_instance.delete_paper.return_value = True
        mock.return_value = mock_instance
        yield mock_instance


# ============================================================================
# Test Helpers
# ============================================================================


def assert_valid_paper_response(response: dict[str, Any]) -> None:
    """Assert that a paper upload response has required fields."""
    assert "pdf_name" in response
    assert "title" in response
    assert "chunk_count" in response
    assert response["chunk_count"] >= 0


def assert_valid_chunk_response(response: dict[str, Any]) -> None:
    """Assert that a chunk list response has required fields."""
    assert "chunks" in response
    assert "total" in response
    assert "page" in response
    assert "limit" in response
    assert isinstance(response["chunks"], list)
