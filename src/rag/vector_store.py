import uuid
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams

from config.settings import config
from src.utils.logger import get_logger
from .embedding import Qwen3VLEmbeddings

logger = get_logger(__name__)

# Namespace UUID for deterministic content-based IDs (UUIDv5).
_NS = uuid.UUID("c0ffeeee-dead-beef-cafe-000000000000")


def _content_uuid(*parts: str) -> str:
    """Return a deterministic UUIDv5 derived from the concatenation of *parts*.

    Using a content-derived ID makes ``upsert`` idempotent: re-ingesting the
    same chunk overwrites the existing point instead of creating a duplicate.
    """
    key = "\x00".join(parts)
    return str(uuid.uuid5(_NS, key))


class PaperVectorStore:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        collection_name: str = "papers_rag",
    ):
        self.client = QdrantClient(
            url=f"http://{config.QDRANT_HOST}:{config.QDRANT_PORT}"
        )
        self.collection_name = collection_name
        self.embeddings = Qwen3VLEmbeddings(model_name_or_path=config.EMBEDDING_MODEL)
        self._ensure_collection()

        self._reranker = None
        if config.RERANKER_MODEL:
            self._load_reranker(config.RERANKER_MODEL)

    def _load_reranker(self, model_path: str) -> None:
        """Lazily load the Qwen3VLReranker. Logs a warning on failure."""
        try:
            from src.custom.qwen3_vl_reranker import Qwen3VLReranker

            self._reranker = Qwen3VLReranker(model_name_or_path=model_path)
            logger.info("Reranker loaded from %s", model_path)
        except Exception as exc:
            logger.warning(
                "Could not load reranker from %s: %s. Skipping reranking.",
                model_path,
                exc,
            )

    def _ensure_collection(self, vector_size: int = None) -> None:
        """Create Qdrant collection if it does not already exist."""
        if vector_size is None:
            vector_size = len(self.embeddings.embed_query("test"))

        collections = self.client.get_collections()
        if not any(col.name == self.collection_name for col in collections.collections):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            logger.info("Created Qdrant collection: %s", self.collection_name)

    def _build_filter(
        self, filter_metadata: Optional[Dict[str, Any]]
    ) -> Optional[models.Filter]:
        """Build a Qdrant exact-match filter from a key-value dict."""
        if not filter_metadata:
            return None
        conditions = [
            models.FieldCondition(key=key, match=models.MatchValue(value=val))
            for key, val in filter_metadata.items()
        ]
        return models.Filter(must=conditions) if conditions else None

    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Re-score *results* with the reranker and return them sorted by reranker score.

        If no reranker is configured, the original list is returned unchanged.
        Each result dict must contain a ``"payload"`` key.
        """
        if self._reranker is None or not results:
            return results

        def _chunk_text(payload: Dict[str, Any]) -> str:
            mm = payload.get("_multimodal_input")
            if mm:
                return mm.get("text", "")
            return payload.get("page_content", "")

        documents = [{"text": _chunk_text(r["payload"])} for r in results]
        try:
            scores = self._reranker.process(
                {"query": {"text": query}, "documents": documents}
            )
        except Exception as exc:
            logger.warning("Reranking failed, returning original order: %s", exc)
            return results

        ranked = sorted(
            zip(scores, results),
            key=lambda x: x[0],
            reverse=True,
        )
        return [{"score": score, "payload": r["payload"]} for score, r in ranked]

    def store_paper_chunks(
        self, chunks: List[str], metadatas: List[Dict[str, Any]]
    ) -> None:
        """Embeds and uploads plain-text chunks to the Qdrant collection."""
        vectors = self.embeddings.embed_documents(chunks)
        points = [
            models.PointStruct(
                id=_content_uuid(
                    metadata.get("pdf_name", ""),
                    str(metadata.get("page_idx", "")),
                    metadata.get("chunk_type", "text"),
                    chunk,
                ),
                vector=vector,
                payload={**metadata, "page_content": chunk},
            )
            for chunk, vector, metadata in zip(chunks, vectors, metadatas)
        ]
        self.client.upsert(collection_name=self.collection_name, points=points)
        logger.info(
            "Stored %d chunks in collection %s.", len(chunks), self.collection_name
        )

    def store_multimodal_inputs(
        self,
        inputs: List[Dict[str, Any]],
        metadatas: List[Dict[str, Any]] = None,
        batch_size: int = 4,
    ) -> None:
        """Embeds and uploads multimodal inputs (text + images) to the Qdrant collection."""
        if metadatas is None:
            metadatas = [{} for _ in range(len(inputs))]

        if len(inputs) != len(metadatas):
            raise ValueError("Number of inputs must match number of metadatas")

        for i in range(0, len(inputs), batch_size):
            batch_inputs = inputs[i : i + batch_size]
            batch_metadatas = metadatas[i : i + batch_size]

            vectors = self.embeddings.embed_inputs(batch_inputs)

            batch_points = [
                models.PointStruct(
                    id=_content_uuid(
                        metadata.get("pdf_name", ""),
                        str(metadata.get("page_idx", "")),
                        metadata.get("chunk_type", ""),
                        inp.get("text", "") if isinstance(inp, dict) else "",
                        metadata.get("img_path", "") if isinstance(inp, dict) else "",
                    ),
                    vector=vector,
                    payload={**metadata, "_multimodal_input": inp},
                )
                for inp, vector, metadata in zip(batch_inputs, vectors, batch_metadatas)
            ]

            self.client.upsert(
                collection_name=self.collection_name, points=batch_points
            )
            logger.info(
                "Upserted batch %d/%d (%d items).",
                i // batch_size + 1,
                -(-len(inputs) // batch_size),
                len(batch_inputs),
            )

        logger.info(
            "Stored %d multimodal items in collection %s.",
            len(inputs),
            self.collection_name,
        )

    def search_similar(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
        rerank: bool = True,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Vector search on the collection using a text query.

        Parameters
        ----------
        query:
            Free-text query string.
        top_k:
            Maximum number of results to return after all filtering.
        filter_metadata:
            Optional Qdrant exact-match metadata filter.
        rerank:
            Whether to apply the reranker (if configured).
        score_threshold:
            Minimum cosine-similarity score (0–1) for a result to be kept.
            Chunks scoring below this value are discarded before reaching the
            LLM.  Defaults to ``config.SCORE_THRESHOLD``; pass ``0.0`` to
            disable filtering for a specific call.
        """
        if score_threshold is None:
            score_threshold = config.SCORE_THRESHOLD

        vector = self.embeddings.embed_query(query)
        filter_params = self._build_filter(filter_metadata)

        # Over-fetch when reranking so the reranker has more candidates to sort.
        fetch_k = top_k * 3 if (rerank and self._reranker) else top_k

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            limit=fetch_k,
            query_filter=filter_params,
        ).points

        raw = [{"score": res.score, "payload": res.payload} for res in results]

        # Discard low-relevance chunks before returning / reranking.
        if score_threshold > 0.0:
            before = len(raw)
            raw = [r for r in raw if r["score"] >= score_threshold]
            if len(raw) < before:
                logger.debug(
                    "Score threshold %.2f removed %d/%d candidates.",
                    score_threshold,
                    before - len(raw),
                    before,
                )

        if rerank and self._reranker:
            raw = self.rerank(query, raw)

        return raw[:top_k]

    def search_by_image(
        self,
        image_path: str,
        instruction: str = None,
        text: str = None,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Vector search on the collection using an image query."""
        vector = self.embeddings.embed_image(
            image_path=image_path, text=text, instruction=instruction
        )
        filter_params = self._build_filter(filter_metadata)

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            limit=top_k,
            query_filter=filter_params,
        ).points

        return [{"score": res.score, "payload": res.payload} for res in results]

    def delete_paper(self, pdf_name: str) -> bool:
        """Delete all chunks associated with a specific paper by pdf_name.

        Returns True if deletion was successful, False otherwise.
        """
        filter_params = self._build_filter({"pdf_name": pdf_name})
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(filter=filter_params),
            )
            logger.info("Deleted points for pdf_name=%s", pdf_name)
            return True
        except Exception as exc:
            logger.error("Failed to delete points for %s: %s", pdf_name, exc)
            return False


# Module-level singleton instance
vector_store = PaperVectorStore()
