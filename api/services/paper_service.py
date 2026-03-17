import os
import shutil
import tempfile
from typing import Any, Optional

from qdrant_client import QdrantClient

from api.config import API_UPLOAD_DIR, API_UPLOAD_DIR as VECTOR_STORE_COLLECTION
from api.schemas import (
    ChunkItem,
    ChunkListResponse,
    PaperDetail,
    PaperItem,
    PaperUploadResponse,
)
from config.settings import config


def _get_qdrant_client():
    return QdrantClient(url=f"http://{config.QDRANT_HOST}:{config.QDRANT_PORT}")


def _get_vector_store():
    from src.rag.vector_store import PaperVectorStore

    return PaperVectorStore()


def _get_parser():
    from src.ingest.mineru_parser import MinerUParser
    from config.settings import config

    return MinerUParser(output_dir="./data/parsed", backend=config.MINERU_BACKEND)


def upload_paper(file_path: str) -> PaperUploadResponse:
    parser = _get_parser()
    parsed_data = parser.parse_pdf(file_path)
    chunks_data, doc_metadata = parser.chunk_content(parsed_data)

    pdf_name = parsed_data.get("pdf_name", "")
    paper_title = doc_metadata.get("title_extracted") or parsed_data.get(
        "title", "Unknown Title"
    )

    _NOISE_TOKENS = (
        "PDF Download",
        "Total Citations",
        "Total Downloads",
        "doi.org",
        "acm.org",
    )
    pre_abstract = doc_metadata.get("pre_abstract_meta", [])
    author_candidates = [
        s
        for s in pre_abstract
        if len(s) <= 120 and "@" not in s and not any(tok in s for tok in _NOISE_TOKENS)
    ]
    authors_str = " | ".join(author_candidates[:3]) if author_candidates else ""

    page_texts: dict[int, list[dict[str, str]]] = {}
    for chunk in chunks_data:
        if chunk.get("type") == "text":
            page_idx = chunk.get("metadata", {}).get("page_idx")
            if page_idx is not None:
                if page_idx not in page_texts:
                    page_texts[page_idx] = []
                page_texts[page_idx].append(
                    {
                        "heading": chunk.get("metadata", {}).get("heading", ""),
                        "text": chunk.get("content", ""),
                    }
                )

    multimodal_inputs = []
    metadata_list = []

    for chunk in chunks_data:
        heading = str(chunk.get("metadata", {}).get("heading", "") or "")
        meta = {
            "title": paper_title,
            "title_normalized": paper_title.casefold(),
            "pdf_name": pdf_name,
            "chunk_type": chunk.get("type", "text"),
            "authors": authors_str,
            "authors_normalized": authors_str.casefold(),
            "backend": parser.backend,
        }
        meta.update(chunk.get("metadata", {}))
        meta.setdefault("has_context_embedding", False)

        input_item: dict = {"text": chunk["content"]}

        chunk_type = chunk.get("type", "")
        if chunk_type in ("image", "table"):
            page_idx = meta.get("page_idx")
            if page_idx is not None:
                context_parts: list[str] = []
                for search_page in [page_idx, page_idx - 1]:
                    if search_page < 0:
                        continue
                    if search_page in page_texts:
                        for text_item in page_texts[search_page]:
                            text_content = text_item.get("text", "")
                            if not text_content:
                                continue
                            import re

                            if re.search(
                                r"\b(Table|Figure|Fig\.?)\s+\d+",
                                text_content,
                                re.IGNORECASE,
                            ):
                                context_parts.append(text_content[:400])
                if context_parts:
                    context_text = "\n[Context] ".join(context_parts)
                    input_item["text"] = (
                        f"[Context] {context_text}\n\n{chunk['content']}"
                    )
                    meta["has_context_embedding"] = True

        if meta.get("img_path"):
            backend_subdir = parser.backend_subdir
            backend_dir = os.path.join(parser.output_dir, pdf_name, backend_subdir)
            img_candidates = [
                os.path.join(backend_dir, meta["img_path"]),
                os.path.join(backend_dir, "images", meta["img_path"]),
            ]
            for img_abs in img_candidates:
                if os.path.exists(img_abs):
                    input_item["image"] = img_abs
                    break

        meta["has_image"] = bool(input_item.get("image")) or bool(meta.get("img_path"))
        meta["has_caption"] = bool(meta.get("caption"))
        meta["has_footnote"] = bool(meta.get("footnote"))

        multimodal_inputs.append(input_item)
        metadata_list.append(meta)

    vector_store = _get_vector_store()
    vector_store.store_multimodal_inputs(multimodal_inputs, metadata_list)

    return PaperUploadResponse(
        pdf_name=pdf_name,
        title=paper_title,
        authors=authors_str,
        chunk_count=len(multimodal_inputs),
        message="Paper uploaded and processed successfully",
    )


def list_papers() -> list[PaperItem]:
    client = _get_qdrant_client()
    collection_name = "papers_rag"

    results = client.scroll(
        collection_name=collection_name,
        scroll_filter=None,
        limit=1000,
        with_payload=True,
        with_vectors=False,
    )[0]

    paper_map: dict[str, dict[str, Any]] = {}
    for point in results:
        payload = point.payload
        pdf_name = payload.get("pdf_name", "") if payload else ""
        if pdf_name and pdf_name not in paper_map:
            paper_map[pdf_name] = {
                "pdf_name": pdf_name,
                "title": payload.get("title", pdf_name) if payload else pdf_name,
                "authors": payload.get("authors", "") if payload else "",
                "chunk_count": 0,
            }
        if pdf_name:
            paper_map[pdf_name]["chunk_count"] += 1

    papers = list(paper_map.values())
    papers.sort(key=lambda x: x["pdf_name"], reverse=True)

    return [PaperItem(**paper) for paper in papers]


def _build_filter(filter_dict):
    if not filter_dict:
        return None

    from qdrant_client.http import models

    conditions = []
    for key, value in filter_dict.items():
        if value is None:
            continue
        if isinstance(value, list):
            conditions.append(
                models.FieldCondition(
                    key=key,
                    match=models.MatchAny(any=value),
                )
            )
        else:
            conditions.append(
                models.FieldCondition(
                    key=key,
                    match=models.MatchValue(value=value),
                )
            )
    return models.Filter(must=conditions) if conditions else None


def get_paper_detail(pdf_name: str) -> Optional[PaperDetail]:
    client = _get_qdrant_client()
    collection_name = "papers_rag"

    results = client.scroll(
        collection_name=collection_name,
        scroll_filter=_build_filter({"pdf_name": pdf_name}),
        limit=1,
        with_payload=True,
        with_vectors=False,
    )[0]

    if not results:
        return None

    payload = results[0].payload
    chunk_count = len(
        client.scroll(
            collection_name=collection_name,
            scroll_filter=_build_filter({"pdf_name": pdf_name}),
            limit=10000,
            with_payload=True,
            with_vectors=False,
        )[0]
    )

    return PaperDetail(
        pdf_name=pdf_name,
        title=payload.get("title", pdf_name) if payload else pdf_name,
        authors=payload.get("authors", "") if payload else "",
        chunk_count=chunk_count,
        metadata={
            "title": payload.get("title") if payload else None,
            "authors": payload.get("authors") if payload else None,
            "chunk_type": payload.get("chunk_type") if payload else None,
            "backend": payload.get("backend") if payload else None,
        },
    )


def get_paper_chunks(
    pdf_name: str,
    page: int = 1,
    limit: int = 20,
    chunk_type: Optional[str] = None,
) -> ChunkListResponse:
    client = _get_qdrant_client()
    collection_name = "papers_rag"

    filters = {"pdf_name": pdf_name}
    if chunk_type:
        filters["chunk_type"] = chunk_type

    all_results = client.scroll(
        collection_name=collection_name,
        scroll_filter=_build_filter(filters),
        limit=10000,
        with_payload=True,
        with_vectors=False,
    )[0]

    total = len(all_results)
    start = (page - 1) * limit
    end = start + limit
    page_results = all_results[start:end]

    chunks = []
    for point in page_results:
        payload = point.payload
        mm_input = payload.get("_multimodal_input", {}) if payload else {}

        chunks.append(
            ChunkItem(
                id=str(point.id),
                content=mm_input.get("text", payload.get("page_content", ""))
                if payload
                else "",
                chunk_type=payload.get("chunk_type", "text") if payload else "text",
                page_idx=payload.get("page_idx") if payload else None,
                heading=payload.get("heading") if payload else None,
                image=mm_input.get("image") if mm_input else None,
            )
        )

    return ChunkListResponse(
        chunks=chunks,
        total=total,
        page=page,
        limit=limit,
    )


def delete_paper(pdf_name: str) -> bool:
    from src.ingest.paper_manager import PaperManager

    manager = PaperManager(output_dir="./data/parsed")
    return manager.delete_paper(pdf_name)


def save_uploaded_file(file_content: bytes, filename: str) -> str:
    os.makedirs(API_UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(API_UPLOAD_DIR, filename)
    with open(file_path, "wb") as f:
        f.write(file_content)
    return file_path


def cleanup_uploaded_file(file_path: str) -> None:
    if os.path.exists(file_path):
        os.remove(file_path)
