from typing import Any

from src.agent import tools


def _make_payload(
    *,
    pdf_name: str = "paper",
    page_idx: int = 0,
    chunk_type: str = "text",
    text: str = "content",
) -> dict[str, Any]:
    return {
        "payload": {
            "metadata": {
                "pdf_name": pdf_name,
                "page_idx": page_idx,
                "chunk_type": chunk_type,
                "title": "Title",
                "authors": "Alice",
                "heading": "Heading",
            },
            "_multimodal_input": {"text": text},
        },
        "score": 0.8,
    }


class _FakeRetrievalService:
    def __init__(self) -> None:
        self.paper_calls = 0
        self.visual_calls = 0
        self.page_calls = 0

    def search_papers(
        self,
        query: str,
        *,
        top_k: int,
        qdrant_filter: Any | None,
        candidate_k: int | None = None,
    ) -> list[dict[str, Any]]:
        _ = query, top_k, qdrant_filter, candidate_k
        self.paper_calls += 1
        return [_make_payload(chunk_type="text", text="paper evidence")]

    def search_visuals(
        self,
        query: str,
        *,
        top_k: int,
        qdrant_filter: Any | None,
        score_threshold: float = 0.0,
        candidate_k: int | None = None,
    ) -> list[dict[str, Any]]:
        _ = query, top_k, qdrant_filter, score_threshold, candidate_k
        self.visual_calls += 1
        return [_make_payload(chunk_type="image", text="visual evidence")]

    def fetch_page_context(
        self,
        qdrant_filter: Any,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        _ = qdrant_filter, limit
        self.page_calls += 1
        return [_make_payload(chunk_type="text", text="local context")]


def test_search_papers_impl_uses_injected_retrieval_service() -> None:
    fake = _FakeRetrievalService()
    tools.QUERY_CACHE.clear()

    result = tools._search_papers_impl(
        query="method",
        top_k=3,
        retrieval_service=fake,
    )

    assert fake.paper_calls == 1
    assert result["tool"] == "search_papers"
    assert len(result["results"]) == 1
    assert result["results"][0]["chunk_type"] == "text"


def test_search_visuals_impl_uses_injected_retrieval_service() -> None:
    fake = _FakeRetrievalService()
    tools.QUERY_CACHE.clear()

    result = tools._search_visuals_impl(
        query="figure",
        chunk_types=["image"],
        top_k=2,
        retrieval_service=fake,
    )

    assert fake.visual_calls == 1
    assert result["tool"] == "search_visuals"
    assert len(result["results"]) == 1
    assert result["results"][0]["chunk_type"] == "image"


def test_get_page_context_impl_uses_injected_retrieval_service() -> None:
    fake = _FakeRetrievalService()
    tools.QUERY_CACHE.clear()

    result = tools._get_page_context_impl(
        pdf_name="paper",
        page_idx=1,
        retrieval_service=fake,
    )

    assert fake.page_calls == 1
    assert result["tool"] == "get_page_context"
    assert len(result["results"]) == 1
    assert result["results"][0]["page_idx"] == 0
