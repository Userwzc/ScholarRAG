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
        batch_size: int = 4,
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

        all_ids: list[str] = []
        total_batches = -(-len(inputs) // batch_size)

        for i in range(0, len(inputs), batch_size):
            batch_inputs = inputs[i : i + batch_size]
            batch_metas = metadatas[i : i + batch_size]
            batch_ids = ids[i : i + batch_size]

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
                i // batch_size + 1,
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

        # 转换格式：Document -> payload dict
        raw = []
        for doc, score in results:
            if score < score_threshold:
                continue
            # 从 Document.metadata 重建 payload
            payload = self._reconstruct_payload(doc)
            raw.append({"score": score, "payload": payload})

        return raw[:k]

    def _reconstruct_payload(self, doc) -> dict[str, Any]:
        """从 Document 重建完整 payload（包含 _multimodal_input）。

        Document.metadata 已经包含了大部分信息，但 _multimodal_input
        需要从 Qdrant 原始 payload 中获取（如果存在）。
        """
        meta = dict(doc.metadata)
        # 移除 LangChain 自动添加的字段
        meta.pop("_id", None)
        meta.pop("_collection_name", None)

        # 尝试从 Qdrant 获取完整 payload（包含 _multimodal_input）
        point_id = doc.metadata.get("_id")
        if point_id:
            try:
                points = self.client.retrieve(
                    self.collection_name,
                    [point_id],
                    with_payload=True,
                )
                if points:
                    return dict(points[0].payload)
            except Exception:
                pass

        # 降级：使用 Document 字段重建
        return {
            self.content_payload_key: doc.page_content,
            self.metadata_payload_key: meta,
        }

    # ========== 图片搜索 ==========

    def search_by_image(
        self,
        image_path: str,
        instruction: str | None = None,
        text: str | None = None,
        k: int = 5,
        filter: models.Filter | None = None,
    ) -> list[dict[str, Any]]:
        """以图搜图/文。

        Args:
            image_path: 图片路径
            instruction: 嵌入指令
            text: 可选的附加文本
            k: 返回数量
            filter: Qdrant Filter

        Returns:
            [{"score": float, "payload": dict}, ...]
        """
        input_dict: dict[str, Any] = {"image": image_path}
        if text:
            input_dict["text"] = text

        vector = self._embeddings.embed_query(
            input_dict,
            instruction=instruction
            or "Retrieve images or text relevant to the user's query.",
        )

        results = self.similarity_search_with_score_by_vector(
            vector,
            k=k,
            filter=filter,
        )

        return [
            {"score": score, "payload": self._reconstruct_payload(doc)}
            for doc, score in results
        ]

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


def _create_vector_store() -> MultimodalQdrantStore:
    """创建 vector_store 实例（延迟初始化，避免 CUDA/vLLM 冲突）。"""
    import torch  # pyright: ignore[reportMissingImports]

    from src.rag.embedding import Qwen3VLEmbeddings

    client = QdrantClient(url=f"http://{config.QDRANT_HOST}:{config.QDRANT_PORT}")

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
