from typing import Any, Protocol


class VectorStoreProtocol(Protocol):
    def similarity_search(
        self,
        query: str,
        k: int,
        filter: Any | None = None,
        score_threshold: float = 0.0,
        candidate_k: int | None = None,
    ) -> list[dict[str, Any]]: ...

    def fetch_by_metadata(
        self, filter: Any, limit: int = 20
    ) -> list[dict[str, Any]]: ...


class RetrievalService(Protocol):
    def search_papers(
        self,
        query: str,
        *,
        top_k: int,
        qdrant_filter: Any | None,
        candidate_k: int | None = None,
    ) -> list[dict[str, Any]]: ...

    def search_visuals(
        self,
        query: str,
        *,
        top_k: int,
        qdrant_filter: Any | None,
        score_threshold: float = 0.0,
        candidate_k: int | None = None,
    ) -> list[dict[str, Any]]: ...

    def fetch_page_context(
        self, qdrant_filter: Any, *, limit: int = 20
    ) -> list[dict[str, Any]]: ...


class VectorStoreRetrievalService:
    def __init__(self, vector_store: VectorStoreProtocol) -> None:
        self._vector_store = vector_store

    def search_papers(
        self,
        query: str,
        *,
        top_k: int,
        qdrant_filter: Any | None,
        candidate_k: int | None = None,
    ) -> list[dict[str, Any]]:
        return self._vector_store.similarity_search(
            query,
            k=top_k,
            filter=qdrant_filter,
            candidate_k=candidate_k if candidate_k is not None else top_k,
        )

    def search_visuals(
        self,
        query: str,
        *,
        top_k: int,
        qdrant_filter: Any | None,
        score_threshold: float = 0.0,
        candidate_k: int | None = None,
    ) -> list[dict[str, Any]]:
        return self._vector_store.similarity_search(
            query,
            k=top_k,
            filter=qdrant_filter,
            score_threshold=score_threshold,
            candidate_k=candidate_k if candidate_k is not None else top_k,
        )

    def fetch_page_context(
        self,
        qdrant_filter: Any,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return self._vector_store.fetch_by_metadata(qdrant_filter, limit=limit)


def get_retrieval_service() -> RetrievalService:
    from src.rag.vector_store import get_vector_store

    return VectorStoreRetrievalService(get_vector_store())
