"""多模态 Qdrant 向量存储，继承 LangChain QdrantVectorStore。

扩展功能：
1. 多模态输入存储（_multimodal_input payload）
2. 确定性 UUIDv5 ID（幂等写入）
3. 图片搜索
4. Hybrid 检索模式（dense + sparse）
"""

import threading
import uuid
from typing import Any

import torch  # pyright: ignore[reportMissingImports]
from langchain_qdrant import QdrantVectorStore, RetrievalMode  # pyright: ignore[reportMissingImports]
from qdrant_client import QdrantClient  # pyright: ignore[reportMissingImports]
from qdrant_client.http import models  # pyright: ignore[reportMissingImports]

from config.settings import config
from src.utils.logger import get_logger

logger = get_logger(__name__)

_NS = uuid.UUID("c0ffeeee-dead-beef-cafe-000000000000")


def _with_current_filter(
    filter_obj: models.Filter | None,
    current_only: bool,
) -> models.Filter | None:
    if not current_only:
        return filter_obj

    current_condition = models.FieldCondition(
        key="metadata.is_current",
        match=models.MatchValue(value=True),
    )

    if filter_obj is None:
        return models.Filter(must=[current_condition])

    must_conditions = list(filter_obj.must or [])
    must_conditions.append(current_condition)
    return models.Filter(
        must=must_conditions,
        should=filter_obj.should,
        must_not=filter_obj.must_not,
        min_should=filter_obj.min_should,
    )


def _content_uuid(*parts: str) -> str:
    """确定性 UUIDv5，用于幂等写入。

    相同内容生成相同 ID，重复 upsert 会覆盖而非创建重复。
    """
    key = "\x00".join(parts)
    return str(uuid.uuid5(_NS, key))


class MultimodalQdrantStore(QdrantVectorStore):
    MULTIMODAL_KEY = "_multimodal_input"

    def __init__(
        self,
        client: QdrantClient,
        collection_name: str,
        embedding: Any,
        sparse_embedding: Any | None = None,
        retrieval_mode: RetrievalMode = RetrievalMode.DENSE,
        **kwargs,
    ):
        """初始化多模态向量存储。

        Args:
            client: Qdrant 客户端
            collection_name: 集合名称
            embedding: 多模态 embedding 实例（必须支持 dict 输入）
            sparse_embedding: 可选的 sparse embedding（HYBRID 模式需要）
            retrieval_mode: 检索模式（DENSE/SPARSE/HYBRID）
        """
        super().__init__(
            client=client,
            collection_name=collection_name,
            embedding=embedding,
            sparse_embedding=sparse_embedding,
            retrieval_mode=retrieval_mode,
            validate_collection_config=False,
            **kwargs,
        )
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """确保 collection 存在，不存在则创建。"""
        if self.client.collection_exists(self.collection_name):
            return

        vector_size = len(self._embeddings.embed_query("test"))

        if self.retrieval_mode == RetrievalMode.DENSE:
            vectors_config = models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            )
            sparse_vectors_config = None
        elif self.retrieval_mode == RetrievalMode.HYBRID:
            vectors_config = models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            )
            sparse_vectors_config = {
                self.sparse_vector_name: models.SparseVectorParams()
            }
        else:  # SPARSE
            vectors_config = None
            sparse_vectors_config = {
                self.sparse_vector_name: models.SparseVectorParams()
            }

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=vectors_config,
            sparse_vectors_config=sparse_vectors_config,
        )
        logger.info("Created Qdrant collection: %s", self.collection_name)

    # ========== 多模态存储 ==========

    def add_multimodal(
        self,
        inputs: list[dict[str, Any]],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
        batch_size: int | None = None,
    ) -> list[str]:
        """存储多模态输入，支持图文混合 embedding。

        Args:
            inputs: 多模态输入列表，每个元素为 dict:
                - {"text": "描述文本"}
                - {"image": "/path/to/image.jpg"}
                - {"text": "描述", "image": "/path/to/image.jpg"}
            metadatas: 元数据列表，与 inputs 一一对应
            ids: 可选的自定义 ID，不提供则生成确定性 UUIDv5
            batch_size: 批处理大小

        Returns:
            存储的 ID 列表
        """
        metadatas = metadatas or [{} for _ in inputs]

        if len(inputs) != len(metadatas):
            raise ValueError("inputs 和 metadatas 长度必须一致")

        # 生成确定性 ID
        if ids is None:
            ids = [
                _content_uuid(
                    m.get("pdf_name", ""),
                    str(m.get("paper_version", "")),
                    str(m.get("page_idx", "")),
                    m.get("chunk_type", ""),
                    inp.get("text", "") if isinstance(inp, dict) else str(inp),
                    m.get("img_path", ""),
                )
                for inp, m in zip(inputs, metadatas)
            ]

        resolved_batch_size = self._resolve_embedding_batch_size(batch_size)

        all_ids: list[str] = []
        total_batches = -(-len(inputs) // resolved_batch_size)

        for i in range(0, len(inputs), resolved_batch_size):
            batch_inputs = inputs[i : i + resolved_batch_size]
            batch_metas = metadatas[i : i + resolved_batch_size]
            batch_ids = ids[i : i + resolved_batch_size]

            # 使用 embedding 生成向量
            vectors = self._embeddings.embed_documents(batch_inputs)

            # 构建 points
            points = []
            for inp, meta, vec, pid in zip(
                batch_inputs, batch_metas, vectors, batch_ids
            ):
                text = inp.get("text", "") if isinstance(inp, dict) else str(inp)
                payload = {
                    self.content_payload_key: text,
                    self.metadata_payload_key: meta,
                    self.MULTIMODAL_KEY: inp,
                }

                # 根据检索模式构建向量结构
                if self.retrieval_mode == RetrievalMode.DENSE:
                    vector_struct = {self.vector_name: vec}
                elif self.retrieval_mode == RetrievalMode.HYBRID:
                    sparse_vec = self.sparse_embeddings.embed_documents([text])[0]
                    vector_struct = {
                        self.vector_name: vec,
                        self.sparse_vector_name: models.SparseVector(
                            indices=sparse_vec.indices,
                            values=sparse_vec.values,
                        ),
                    }
                else:  # SPARSE
                    sparse_vec = self.sparse_embeddings.embed_documents([text])[0]
                    vector_struct = {
                        self.sparse_vector_name: models.SparseVector(
                            indices=sparse_vec.indices,
                            values=sparse_vec.values,
                        ),
                    }

                points.append(
                    models.PointStruct(
                        id=pid,
                        vector=vector_struct,
                        payload=payload,
                    )
                )

            self.client.upsert(self.collection_name, points=points)
            all_ids.extend(batch_ids)
            logger.info(
                "Upserted batch %d/%d (%d items)",
                i // resolved_batch_size + 1,
                total_batches,
                len(batch_inputs),
            )
            torch.cuda.empty_cache()

        logger.info(
            "Stored %d multimodal items in collection %s",
            len(inputs),
            self.collection_name,
        )
        return all_ids

    def _resolve_embedding_batch_size(self, batch_size: int | None) -> int:
        requested = (
            batch_size if batch_size is not None else config.EMBEDDING_BATCH_SIZE
        )
        requested = max(1, int(requested))
        if not torch.cuda.is_available():
            return requested

        try:
            free_bytes, _ = torch.cuda.mem_get_info()
        except RuntimeError:
            return requested

        model_name = str(getattr(config, "EMBEDDING_MODEL", "")).lower()
        if "72b" in model_name or "32b" in model_name:
            model_scale = 8
        elif "14b" in model_name or "13b" in model_name:
            model_scale = 4
        elif "7b" in model_name:
            model_scale = 2
        else:
            model_scale = 1

        estimated_per_sample = 256 * 1024 * 1024 * model_scale
        safe_limit = int((free_bytes * 0.7) // estimated_per_sample)
        if safe_limit <= 0:
            return 1
        return min(requested, safe_limit)

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter: models.Filter | None = None,
        score_threshold: float = 0.0,
        candidate_k: int | None = None,
        current_only: bool = True,
    ) -> list[dict[str, Any]]:
        """默认使用 hybrid retrieval 的向量搜索，返回原始 payload 格式。

        Args:
            query: 查询文本
            k: 返回结果数量
            filter: Qdrant Filter 对象
            score_threshold: 分数阈值（低于此值的结果被过滤）
            candidate_k: 候选数量，不指定时自动设为 k

        Returns:
            [{"score": float, "payload": dict}, ...]
        """
        fetch_k = candidate_k
        if fetch_k is None:
            fetch_k = k

        qdrant_filter = _with_current_filter(filter, current_only=current_only)

        # 调用父类搜索
        results = self.similarity_search_with_score(
            query,
            k=fetch_k,
            filter=qdrant_filter,
            score_threshold=score_threshold if score_threshold > 0 else None,
        )

        docs = [doc for doc, _ in results]
        payloads = self._reconstruct_payloads(docs)

        raw = []
        for (doc, score), payload in zip(results, payloads):
            if score < score_threshold:
                continue
            raw.append({"score": score, "payload": payload})

        return raw[:k]

    def _reconstruct_payloads(self, docs: list[Any]) -> list[dict[str, Any]]:
        payload_by_id: dict[str, dict[str, Any]] = {}
        point_ids: list[Any] = []
        point_id_keys: list[str] = []

        for doc in docs:
            point_id = doc.metadata.get("_id")
            if point_id is None:
                continue
            key = str(point_id)
            if key in payload_by_id:
                continue
            point_id_keys.append(key)
            point_ids.append(point_id)

        if point_ids:
            try:
                points = self.client.retrieve(
                    self.collection_name,
                    point_ids,
                    with_payload=True,
                )
                for key, point in zip(point_id_keys, points):
                    if getattr(point, "payload", None):
                        payload_by_id[key] = dict(point.payload)
            except (RuntimeError, ValueError):
                payload_by_id = {}

        return [self._reconstruct_payload(doc, payload_by_id) for doc in docs]

    def _reconstruct_payload(
        self,
        doc: Any,
        payload_by_id: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        meta = dict(doc.metadata)
        point_id = doc.metadata.get("_id")
        if point_id is not None and payload_by_id:
            payload = payload_by_id.get(str(point_id))
            if payload is not None:
                return payload

        meta.pop("_id", None)
        meta.pop("_collection_name", None)
        return {
            self.content_payload_key: doc.page_content,
            self.metadata_payload_key: meta,
        }

    # ========== 元数据操作 ==========

    def mark_paper_chunks_non_current(
        self,
        pdf_name: str,
        keep_version: int,
        batch_size: int = 256,
    ) -> int:
        selector = models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.pdf_name",
                    match=models.MatchValue(value=pdf_name),
                )
            ]
        )

        updated_count = 0
        offset: Any | None = None
        while True:
            points, next_offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=selector,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )

            if not points:
                break

            updated_points: list[models.PointStruct] = []
            for point in points:
                payload = dict(point.payload or {})
                metadata = dict(payload.get(self.metadata_payload_key, {}) or {})

                if metadata.get("paper_version") == keep_version:
                    continue
                if metadata.get("is_current") is False:
                    continue

                metadata["is_current"] = False
                payload[self.metadata_payload_key] = metadata
                updated_points.append(
                    models.PointStruct(
                        id=point.id,
                        vector=point.vector,
                        payload=payload,
                    )
                )

            if updated_points:
                self.client.upsert(self.collection_name, points=updated_points)
                updated_count += len(updated_points)

            if next_offset is None:
                break
            offset = next_offset

        return updated_count

    def fetch_by_metadata(
        self,
        filter: models.Filter,
        limit: int = 20,
        current_only: bool = True,
    ) -> list[dict[str, Any]]:
        """按元数据获取 points（无向量搜索）。

        Args:
            filter: Qdrant Filter 对象
            limit: 最大返回数量

        Returns:
            [{"payload": dict}, ...]
        """
        qdrant_filter = _with_current_filter(filter, current_only=current_only)
        points, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=qdrant_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [{"payload": p.payload} for p in points]

    def scroll_chunks(
        self,
        filter: models.Filter | None = None,
        limit: int = 10000,
        offset: Any | None = None,
        current_only: bool = True,
    ) -> tuple[list[dict[str, Any]], Any | None]:
        """分页滚动获取 chunks。

        Args:
            filter: Qdrant Filter 对象
            limit: 每页数量
            offset: 分页偏移（由上一次调用返回）

        Returns:
            (results, next_offset)
        """
        qdrant_filter = _with_current_filter(filter, current_only=current_only)
        points, next_offset = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=qdrant_filter,
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        return [{"id": p.id, "payload": p.payload} for p in points], next_offset

    def delete_by_metadata(
        self,
        filter: models.Filter,
    ) -> bool:
        """按元数据删除 points。

        Args:
            filter: Qdrant Filter 对象

        Returns:
            是否成功
        """
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(filter=filter),
            )
            logger.info("Deleted points matching filter")
            return True
        except Exception as exc:
            logger.error("Failed to delete points: %s", exc)
            return False

    def delete_paper(self, pdf_name: str) -> bool:
        """删除指定论文的所有 chunks。

        Args:
            pdf_name: 论文名称（不含 .pdf 后缀）

        Returns:
            是否成功
        """
        filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.pdf_name", match=models.MatchValue(value=pdf_name)
                )
            ]
        )
        return self.delete_by_metadata(filter)

    def get_all_papers(
        self,
        filter: models.Filter | None = None,
        current_only: bool = True,
    ) -> list[dict[str, Any]]:
        """获取所有 chunks 的 payload（用于提取论文列表）。"""
        qdrant_filter = _with_current_filter(filter, current_only=current_only)
        points, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=qdrant_filter,
            limit=10000,
            with_payload=True,
            with_vectors=False,
        )
        return [{"payload": p.payload} for p in points]

    def count_chunks(
        self,
        filter: models.Filter | None = None,
        current_only: bool = True,
    ) -> int:
        """统计 chunks 数量。

        Args:
            filter: 可选的 Qdrant Filter

        Returns:
            匹配的 chunk 数量
        """
        qdrant_filter = _with_current_filter(filter, current_only=current_only)
        return self.client.count(
            collection_name=self.collection_name,
            count_filter=qdrant_filter,
            exact=True,
        ).count


# ========== 模块级单例（延迟初始化） ==========

_vector_store: MultimodalQdrantStore | None = None
_vector_store_lock = threading.Lock()
_qdrant_client: QdrantClient | None = None
_qdrant_client_lock = threading.Lock()


def _get_qdrant_client() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        with _qdrant_client_lock:
            if _qdrant_client is None:
                client_kwargs: dict[str, Any] = {
                    "url": f"http://{config.QDRANT_HOST}:{config.QDRANT_PORT}",
                    "timeout": config.QDRANT_TIMEOUT_SECONDS,
                }
                try:
                    import httpx  # pyright: ignore[reportMissingImports]

                    client_kwargs["limits"] = httpx.Limits(
                        max_keepalive_connections=config.QDRANT_HTTP_KEEPALIVE_CONNECTIONS,
                        max_connections=config.QDRANT_HTTP_MAX_CONNECTIONS,
                    )
                    _qdrant_client = QdrantClient(**client_kwargs)
                except TypeError:
                    client_kwargs.pop("limits", None)
                    _qdrant_client = QdrantClient(**client_kwargs)
    return _qdrant_client


def _create_vector_store() -> MultimodalQdrantStore:
    """创建 vector_store 实例（延迟初始化，避免 CUDA/vLLM 冲突）。"""
    import torch  # pyright: ignore[reportMissingImports]

    from src.rag.embedding import Qwen3VLEmbeddings

    client = _get_qdrant_client()

    embeddings = Qwen3VLEmbeddings(
        model_name_or_path=config.EMBEDDING_MODEL,
        torch_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
    )

    # Sparse embedding（HYBRID 模式）
    sparse_embedding = None
    retrieval_mode = RetrievalMode.DENSE
    if getattr(config, "ENABLE_HYBRID", False):
        try:
            from langchain_qdrant import FastEmbedSparse  # pyright: ignore[reportMissingImports]

            sparse_embedding = FastEmbedSparse(model_name="Qdrant/bm25")
            retrieval_mode = RetrievalMode.HYBRID
            logger.info("Hybrid mode enabled with FastEmbed sparse")
        except Exception as exc:
            logger.warning(
                "Could not load sparse embedding, falling back to DENSE: %s", exc
            )

    return MultimodalQdrantStore(
        client=client,
        collection_name=config.QDRANT_COLLECTION_NAME,
        embedding=embeddings,
        sparse_embedding=sparse_embedding,
        retrieval_mode=retrieval_mode,
    )


def get_vector_store() -> MultimodalQdrantStore:
    """获取 vector_store 单例（线程安全）。"""
    global _vector_store
    if _vector_store is None:
        with _vector_store_lock:
            if _vector_store is None:
                _vector_store = _create_vector_store()
    return _vector_store


# 向后兼容：保留旧的全局变量名（但改为函数调用）
# 注意：直接使用 `vector_store` 会返回 None，需要改用 `get_vector_store()`
vector_store = None  # type: ignore[assignment]
