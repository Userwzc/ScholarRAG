"""LangGraph Agent tools for paper RAG."""

# pyright: reportMissingImports=false, reportUndefinedVariable=false

import hashlib
import os
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from qdrant_client.http import models

from config.settings import config
from src.agent.retrieval_service import RetrievalService, get_retrieval_service
from src.utils.cache import QueryCache
from src.utils.exceptions import AppError, ExternalServiceError
from src.utils.logger import get_logger
from src.utils.metrics import record_search

logger = get_logger(__name__)
QUERY_CACHE = QueryCache(ttl=300)


def _resolve_img_path(pdf_name: str, img_path: str) -> str:
    """Resolve MinerU-stored image names to absolute paths when possible."""
    if not img_path:
        return ""
    if os.path.isabs(img_path) and os.path.exists(img_path):
        return img_path

    base_dir = os.path.join(config.PARSED_OUTPUT_DIR, pdf_name)
    for backend_subdir in ("auto", "hybrid_auto"):
        backend_dir = os.path.join(base_dir, backend_subdir)
        for candidate in (
            os.path.join(backend_dir, img_path),
            os.path.join(backend_dir, "images", img_path),
        ):
            if os.path.exists(candidate):
                return os.path.abspath(candidate)

    return img_path


def _evidence_id(
    pdf_name: str,
    page_idx: Any,
    chunk_type: str,
    text: str,
    img_path: str,
) -> str:
    """Generate a short unique ID for an evidence chunk."""
    raw = "\x00".join(
        [pdf_name, str(page_idx), chunk_type, text[:500], img_path]
    ).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


class SearchPapersInput(BaseModel):
    """Input schema for search_papers tool."""

    query: str = Field(
        description="Semantic query for paper content, methodology, findings, or concepts."
    )
    filter_metadata: str = Field(
        default="{}",
        description=(
            "Optional JSON-formatted exact-match metadata filter, for example "
            '{"pdf_name": "DREAM"}.'
        ),
    )
    pdf_name: str = Field(default="", description="Optional exact paper name filter.")
    chunk_types: list[str] = Field(
        default_factory=list,
        description="Optional chunk types to keep, e.g. text, table, image, code, title.",
    )
    page_idx: int | None = Field(default=None, description="Optional exact page index.")
    page_start: int | None = Field(
        default=None, description="Optional page range start."
    )
    page_end: int | None = Field(default=None, description="Optional page range end.")
    heading_contains: str = Field(
        default="",
        description="Optional case-insensitive substring filter on heading/section path.",
    )
    authors_contains: str = Field(
        default="",
        description="Optional case-insensitive substring filter on authors.",
    )
    title_contains: str = Field(
        default="",
        description="Optional case-insensitive substring filter on title.",
    )
    figure_or_table_label: str = Field(
        default="",
        description="Optional exact/substring filter for labels like Table 3 or Figure 4.",
    )
    top_k: int = Field(
        default=config.RAG_TOP_K, description="Number of results to return."
    )


class SearchVisualsInput(BaseModel):
    """Input schema for search_visuals tool."""

    query: str = Field(
        description="Query for figures, tables, captions, ablations, or experimental results."
    )
    pdf_name: str = Field(
        default="",
        description="Optional paper name without .pdf to constrain the search.",
    )
    chunk_types: list[str] = Field(
        default_factory=list,
        description="Optional visual chunk types, usually table and/or image.",
    )
    page_idx: int | None = Field(default=None, description="Optional exact page index.")
    page_start: int | None = Field(
        default=None, description="Optional page range start."
    )
    page_end: int | None = Field(default=None, description="Optional page range end.")
    heading_contains: str = Field(
        default="",
        description="Optional case-insensitive substring filter on heading/section path.",
    )
    figure_or_table_label: str = Field(
        default="",
        description="Optional exact/substring filter for labels like Table 3 or Figure 4.",
    )
    top_k: int = Field(
        default=config.RAG_TOP_K, description="Number of results to return."
    )


class PageContextInput(BaseModel):
    """Input schema for get_page_context tool."""

    pdf_name: str = Field(description="Paper name without .pdf extension.")
    page_idx: int = Field(description="Zero-based page index to inspect.")
    heading: str = Field(
        default="",
        description="Optional heading substring to narrow context to a section.",
    )


def _build_qdrant_filter(
    pdf_name: str = "",
    chunk_types: list[str] | None = None,
    page_idx: int | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
    filter_metadata: str = "{}",
) -> models.Filter | None:
    """构建 Qdrant Filter 对象。

    Args:
        pdf_name: 论文名称过滤
        chunk_types: chunk 类型列表过滤
        page_idx: 精确页码过滤
        page_start/page_end: 页码范围过滤
        filter_metadata: JSON 格式的额外元数据过滤条件

    Returns:
        models.Filter 对象，无条件时返回 None
    """
    import json

    must_conditions: list[models.Condition] = []

    # 解析 filter_metadata JSON 并添加条件
    if filter_metadata and filter_metadata != "{}":
        try:
            extra_filters = json.loads(filter_metadata)
            for key, value in extra_filters.items():
                if value is not None and value != "":
                    must_conditions.append(
                        models.FieldCondition(
                            key=f"metadata.{key}",
                            match=models.MatchValue(value=value),
                        )
                    )
        except json.JSONDecodeError:
            logger.warning("Invalid filter_metadata JSON: %s", filter_metadata)

    if pdf_name:
        must_conditions.append(
            models.FieldCondition(
                key="metadata.pdf_name",
                match=models.MatchValue(value=pdf_name),
            )
        )

    if page_idx is not None:
        must_conditions.append(
            models.FieldCondition(
                key="metadata.page_idx",
                match=models.MatchValue(value=page_idx),
            )
        )
    elif page_start is not None or page_end is not None:
        must_conditions.append(
            models.FieldCondition(
                key="metadata.page_idx",
                range=models.Range(gte=page_start, lte=page_end),
            )
        )

    if chunk_types:
        if len(chunk_types) == 1:
            must_conditions.append(
                models.FieldCondition(
                    key="metadata.chunk_type",
                    match=models.MatchValue(value=chunk_types[0]),
                )
            )
        else:
            must_conditions.append(
                models.FieldCondition(
                    key="metadata.chunk_type",
                    match=models.MatchAny(any=chunk_types),
                )
            )

    return models.Filter(must=must_conditions) if must_conditions else None


def _contains(haystack: Any, needle: str) -> bool:
    """Case-insensitive substring check."""
    if not needle:
        return True
    return needle.casefold() in str(haystack or "").casefold()


def _within_page_range(
    payload: dict[str, Any], page_start: int | None, page_end: int | None
) -> bool:
    """Check if payload's page_idx falls within the specified range."""
    if page_start is None and page_end is None:
        return True
    meta = payload.get("metadata", {})
    page_idx = meta.get("page_idx")
    if not isinstance(page_idx, int):
        return False
    if page_start is not None and page_idx < page_start:
        return False
    if page_end is not None and page_idx > page_end:
        return False
    return True


def _matches_filters(
    payload: dict[str, Any],
    *,
    chunk_types: list[str] | None = None,
    heading_contains: str = "",
    authors_contains: str = "",
    title_contains: str = "",
    figure_or_table_label: str = "",
    page_start: int | None = None,
    page_end: int | None = None,
) -> bool:
    """Check if payload matches all client-side filters."""
    meta = payload.get("metadata", {})
    if chunk_types and str(meta.get("chunk_type", "")) not in chunk_types:
        return False
    heading = meta.get("section_path") or meta.get("heading", "")
    if not _contains(heading, heading_contains):
        return False
    if not _contains(meta.get("authors", ""), authors_contains):
        return False
    if not _contains(meta.get("title", ""), title_contains):
        return False
    if not _contains(meta.get("figure_or_table_label", ""), figure_or_table_label):
        return False
    if not _within_page_range(payload, page_start, page_end):
        return False
    return True


def _payload_to_evidence(
    payload: dict[str, Any],
    score: float,
    source_tool: str,
) -> dict[str, Any]:
    """从 Qdrant payload 转换为 evidence 格式。"""
    mm = payload.get("_multimodal_input")
    if mm is not None:
        chunk = mm.get("text", "")
    else:
        chunk = payload.get("page_content", "")

    meta = payload.get("metadata", {})

    title = meta.get("title", "Unknown Title")
    pdf_name = meta.get("pdf_name", "")
    authors = meta.get("authors", "")
    page_idx = meta.get("page_idx", "")
    chunk_type = meta.get("chunk_type", "text")
    heading = meta.get("heading", "")
    caption = meta.get("caption", "")
    footnote = meta.get("footnote", "")
    img_path = meta.get("img_path", "")
    if mm is not None and not img_path:
        img_path = mm.get("image", "")
    img_path = _resolve_img_path(pdf_name, img_path)

    return {
        "evidence_id": _evidence_id(
            pdf_name=pdf_name,
            page_idx=page_idx,
            chunk_type=chunk_type,
            text=chunk,
            img_path=img_path,
        ),
        "title": title,
        "pdf_name": pdf_name,
        "authors": authors,
        "page_idx": page_idx,
        "chunk_type": chunk_type,
        "heading": heading,
        "section_path": meta.get("section_path", heading),
        "section_depth": meta.get("section_depth", 0),
        "local_label": meta.get("local_label", ""),
        "score": round(score, 6),
        "text": chunk,
        "img_path": img_path,
        "has_image": meta.get("has_image", bool(img_path)),
        "has_caption": meta.get("has_caption", bool(caption)),
        "caption": caption,
        "footnote": footnote,
        "figure_or_table_label": meta.get("figure_or_table_label", ""),
        "chunk_order": meta.get("chunk_order", -1),
        "page_chunk_order": meta.get("page_chunk_order", -1),
        "source_tool": source_tool,
    }


def _results_json(
    query: str,
    source_tool: str,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Wrap results in a standard JSON structure."""
    return {"query": query, "tool": source_tool, "results": results}


def _format_results(
    results: list[dict[str, Any]],
    source_tool: str,
) -> list[dict[str, Any]]:
    """Convert list of results to evidence format."""
    return [
        _payload_to_evidence(doc.get("payload", {}), doc.get("score", 0.0), source_tool)
        for doc in results
    ]


def _visual_key(item: dict[str, Any]) -> tuple[str, str, str]:
    """Generate a deduplication key for visual chunks."""
    payload = item.get("payload", {})
    meta = payload.get("metadata", {})
    pdf_name = str(meta.get("pdf_name", ""))
    page_idx = str(meta.get("page_idx", ""))
    label = str(meta.get("figure_or_table_label", "") or meta.get("img_path", ""))
    return pdf_name, page_idx, label


def _visual_rank(item: dict[str, Any]) -> tuple[float, int, int, int]:
    """Generate a sort key for ranking visual chunks."""
    payload = item.get("payload", {})
    meta = payload.get("metadata", {})
    return (
        float(item.get("score", 0.0)),
        1 if meta.get("chunk_type") == "table" else 0,
        1 if meta.get("has_caption") else 0,
        1 if meta.get("has_image") else 0,
    )


def _search_papers_impl(
    query: str,
    filter_metadata: str = "{}",
    pdf_name: str = "",
    chunk_types: list[str] | None = None,
    page_idx: int | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
    heading_contains: str = "",
    authors_contains: str = "",
    title_contains: str = "",
    figure_or_table_label: str = "",
    top_k: int = config.RAG_TOP_K,
    retrieval_service: RetrievalService | None = None,
) -> dict[str, Any]:
    qdrant_filter = _build_qdrant_filter(
        pdf_name=pdf_name,
        chunk_types=chunk_types,
        page_idx=page_idx,
        page_start=page_start,
        page_end=page_end,
        filter_metadata=filter_metadata,
    )
    cache_filters: dict[str, Any] = {
        "tool": "search_papers",
        "filter_metadata": filter_metadata,
        "pdf_name": pdf_name,
        "chunk_types": chunk_types or [],
        "page_idx": page_idx,
        "page_start": page_start,
        "page_end": page_end,
        "heading_contains": heading_contains,
        "authors_contains": authors_contains,
        "title_contains": title_contains,
        "figure_or_table_label": figure_or_table_label,
        "top_k": top_k,
    }
    cached_results = QUERY_CACHE.get(query, cache_filters)
    if cached_results is not None:
        return _results_json(query, "search_papers", cached_results)

    service = retrieval_service or get_retrieval_service()
    try:
        with record_search("search_papers"):
            results = service.search_papers(
                query,
                top_k=top_k,
                qdrant_filter=qdrant_filter,
                candidate_k=top_k,
            )
    except AppError as exc:
        logger.error("Vector store search failed: %s", exc)
        return _results_json(query, "search_papers", [])
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        error = ExternalServiceError("Vector store search failed", log_message=str(exc))
        logger.error("%s: %s", error.message, exc)
        return _results_json(query, "search_papers", [])

    filtered = [
        doc
        for doc in results
        if _matches_filters(
            doc.get("payload", {}),
            chunk_types=chunk_types,
            heading_contains=heading_contains,
            authors_contains=authors_contains,
            title_contains=title_contains,
            figure_or_table_label=figure_or_table_label,
            page_start=page_start,
            page_end=page_end,
        )
    ]
    filtered.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    formatted = _format_results(filtered[:top_k], "search_papers")
    QUERY_CACHE.set(query, cache_filters, formatted)
    return _results_json(query, "search_papers", formatted)


def _search_visuals_impl(
    query: str,
    pdf_name: str = "",
    chunk_types: list[str] | None = None,
    page_idx: int | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
    heading_contains: str = "",
    figure_or_table_label: str = "",
    top_k: int = config.RAG_TOP_K,
    retrieval_service: RetrievalService | None = None,
) -> dict[str, Any]:
    combined: list[dict[str, Any]] = []
    seen_ids: set[tuple[str, str, str]] = set()

    visual_chunk_types = chunk_types or ["table", "image"]
    visual_query = query
    if (
        figure_or_table_label
        and figure_or_table_label.casefold() not in query.casefold()
    ):
        visual_query = f"{query} {figure_or_table_label}"

    cache_filters: dict[str, Any] = {
        "tool": "search_visuals",
        "pdf_name": pdf_name,
        "chunk_types": chunk_types or [],
        "page_idx": page_idx,
        "page_start": page_start,
        "page_end": page_end,
        "heading_contains": heading_contains,
        "figure_or_table_label": figure_or_table_label,
        "top_k": top_k,
    }
    cached_results = QUERY_CACHE.get(visual_query, cache_filters)
    if cached_results is not None:
        return _results_json(visual_query, "search_visuals", cached_results)

    service = retrieval_service or get_retrieval_service()
    for chunk_type in visual_chunk_types:
        qdrant_filter = _build_qdrant_filter(
            pdf_name=pdf_name,
            page_idx=page_idx,
            chunk_types=[chunk_type],
            page_start=page_start,
            page_end=page_end,
        )
        try:
            with record_search("search_visuals"):
                results = service.search_visuals(
                    visual_query,
                    top_k=max(4, top_k * 3),
                    qdrant_filter=qdrant_filter,
                    score_threshold=0.0,
                    candidate_k=top_k,
                )
        except AppError as exc:
            logger.error("Visual search failed for %s: %s", chunk_type, exc)
            continue
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            error = ExternalServiceError("Visual search failed", log_message=str(exc))
            logger.error("%s for %s: %s", error.message, chunk_type, exc)
            continue

        filtered = [
            doc
            for doc in results
            if _matches_filters(
                doc.get("payload", {}),
                chunk_types=visual_chunk_types,
                heading_contains=heading_contains,
                figure_or_table_label=figure_or_table_label,
                page_start=page_start,
                page_end=page_end,
            )
        ]
        filtered.sort(key=_visual_rank, reverse=True)

        for doc in filtered:
            visual_key = _visual_key(doc)
            if visual_key in seen_ids:
                continue
            seen_ids.add(visual_key)
            combined.append(
                _payload_to_evidence(
                    doc.get("payload", {}),
                    doc.get("score", 0.0),
                    "search_visuals",
                )
            )

    combined.sort(
        key=lambda item: (
            float(item.get("score", 0.0)),
            1 if item.get("chunk_type") == "table" else 0,
            1 if item.get("has_caption") else 0,
        ),
        reverse=True,
    )
    limited = combined[:top_k]
    QUERY_CACHE.set(visual_query, cache_filters, limited)
    return _results_json(visual_query, "search_visuals", limited)


def _get_page_context_impl(
    pdf_name: str,
    page_idx: int,
    heading: str = "",
    retrieval_service: RetrievalService | None = None,
) -> dict[str, Any]:
    qdrant_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="metadata.pdf_name",
                match=models.MatchValue(value=pdf_name),
            ),
            models.FieldCondition(
                key="metadata.page_idx",
                match=models.MatchValue(value=page_idx),
            ),
        ]
    )
    service = retrieval_service or get_retrieval_service()
    try:
        with record_search("get_page_context"):
            results = service.fetch_page_context(qdrant_filter, limit=20)
    except AppError as exc:
        logger.error("Page-context fetch failed: %s", exc)
        return _results_json(f"{pdf_name}:{page_idx}", "get_page_context", [])
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        error = ExternalServiceError("Page-context fetch failed", log_message=str(exc))
        logger.error("%s: %s", error.message, exc)
        return _results_json(f"{pdf_name}:{page_idx}", "get_page_context", [])

    formatted: list[dict[str, Any]] = []
    for doc in results:
        payload = doc.get("payload", {})
        meta = payload.get("metadata", {})
        payload_heading = str(meta.get("heading", ""))
        if heading and payload_heading and heading not in payload_heading:
            continue
        formatted.append(_payload_to_evidence(payload, 1.0, "get_page_context"))

    formatted.sort(
        key=lambda item: (
            int(item.get("page_chunk_order", 10**9)),
            int(item.get("chunk_order", 10**9)),
            str(item.get("heading", "")),
        )
    )
    return _results_json(f"{pdf_name}:{page_idx}", "get_page_context", formatted)


@tool("search_papers", args_schema=SearchPapersInput)
def search_papers(
    query: str,
    filter_metadata: str = "{}",
    pdf_name: str = "",
    chunk_types: list[str] | None = None,
    page_idx: int | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
    heading_contains: str = "",
    authors_contains: str = "",
    title_contains: str = "",
    figure_or_table_label: str = "",
    top_k: int = config.RAG_TOP_K,
) -> dict[str, Any]:
    return _search_papers_impl(
        query=query,
        filter_metadata=filter_metadata,
        pdf_name=pdf_name,
        chunk_types=chunk_types,
        page_idx=page_idx,
        page_start=page_start,
        page_end=page_end,
        heading_contains=heading_contains,
        authors_contains=authors_contains,
        title_contains=title_contains,
        figure_or_table_label=figure_or_table_label,
        top_k=top_k,
    )


@tool("search_visuals", args_schema=SearchVisualsInput)
def search_visuals(
    query: str,
    pdf_name: str = "",
    chunk_types: list[str] | None = None,
    page_idx: int | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
    heading_contains: str = "",
    figure_or_table_label: str = "",
    top_k: int = config.RAG_TOP_K,
) -> dict[str, Any]:
    return _search_visuals_impl(
        query=query,
        pdf_name=pdf_name,
        chunk_types=chunk_types,
        page_idx=page_idx,
        page_start=page_start,
        page_end=page_end,
        heading_contains=heading_contains,
        figure_or_table_label=figure_or_table_label,
        top_k=top_k,
    )


@tool("get_page_context", args_schema=PageContextInput)
def get_page_context(
    pdf_name: str,
    page_idx: int,
    heading: str = "",
) -> dict[str, Any]:
    return _get_page_context_impl(
        pdf_name=pdf_name,
        page_idx=page_idx,
        heading=heading,
    )
