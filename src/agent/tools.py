import hashlib
import json
import os
from typing import Any

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from config.settings import config
from src.rag.vector_store import vector_store
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _resolve_img_path(pdf_name: str, img_path: str) -> str:
    """Resolve MinerU-stored image names to absolute paths when possible."""
    if not img_path:
        return ""
    if os.path.isabs(img_path) and os.path.exists(img_path):
        return img_path

    base_dir = os.path.join("./data/parsed", pdf_name)
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
    raw = "\x00".join(
        [pdf_name, str(page_idx), chunk_type, text[:500], img_path]
    ).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def _parse_filter_metadata(filter_metadata: str) -> dict[str, Any] | None:
    metadata_dict: dict[str, Any] | None = None
    try:
        parsed = json.loads(filter_metadata)
        if isinstance(parsed, dict) and parsed:
            metadata_dict = parsed
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Could not parse filter_metadata JSON, ignoring filter: %s", exc)
    return metadata_dict


def _payload_to_evidence(
    payload: dict[str, Any],
    score: float,
    source_tool: str,
) -> dict[str, Any]:
    mm = payload.get("_multimodal_input")
    if mm is not None:
        chunk = mm.get("text", "")
    else:
        chunk = payload.get("page_content", "")

    title = payload.get("title", "Unknown Title")
    pdf_name = payload.get("pdf_name", "")
    authors = payload.get("authors", "")
    page_idx = payload.get("page_idx", "")
    chunk_type = payload.get("chunk_type", "text")
    heading = payload.get("heading", "")
    caption = payload.get("caption", "")
    footnote = payload.get("footnote", "")
    img_path = payload.get("img_path", "")
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
        "section_path": payload.get("section_path", heading),
        "section_depth": payload.get("section_depth", 0),
        "local_label": payload.get("local_label", ""),
        "score": round(score, 6),
        "text": chunk,
        "img_path": img_path,
        "has_image": payload.get("has_image", bool(img_path)),
        "has_caption": payload.get("has_caption", bool(caption)),
        "caption": caption,
        "footnote": footnote,
        "figure_or_table_label": payload.get("figure_or_table_label", ""),
        "chunk_order": payload.get("chunk_order", -1),
        "page_chunk_order": payload.get("page_chunk_order", -1),
        "source_tool": source_tool,
    }


def _results_json(
    query: str,
    source_tool: str,
    results: list[dict[str, Any]],
) -> str:
    return json.dumps(
        {"query": query, "tool": source_tool, "results": results},
        ensure_ascii=False,
    )


class SearchPapersInput(BaseModel):
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
    pdf_name: str = Field(description="Paper name without .pdf extension.")
    page_idx: int = Field(description="Zero-based page index to inspect.")
    heading: str = Field(
        default="",
        description="Optional heading substring to narrow context to a section.",
    )


def _merge_exact_filters(
    filter_metadata: str,
    pdf_name: str = "",
    page_idx: int | None = None,
    chunk_types: list[str] | None = None,
) -> dict[str, Any] | None:
    exact_filter = _parse_filter_metadata(filter_metadata) or {}
    if pdf_name:
        exact_filter["pdf_name"] = pdf_name
    if page_idx is not None:
        exact_filter["page_idx"] = page_idx
    if chunk_types and len(chunk_types) == 1:
        exact_filter["chunk_type"] = chunk_types[0]
    return exact_filter or None


def _build_structured_filter(
    filter_metadata: str,
    *,
    pdf_name: str = "",
    chunk_types: list[str] | None = None,
    page_idx: int | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
) -> dict[str, Any] | None:
    """Build richer filter metadata for vector_store._build_filter()."""
    base = _parse_filter_metadata(filter_metadata)
    if base and any(key in base for key in ("must", "should", "must_not")):
        spec = dict(base)
    else:
        spec = {"must": []}
        if base:
            for key, value in base.items():
                spec["must"].append({"key": key, "match": value})

    must = spec.setdefault("must", [])
    if pdf_name:
        must.append({"key": "pdf_name", "match": pdf_name})
    if page_idx is not None:
        must.append({"key": "page_idx", "match": page_idx})
    elif page_start is not None or page_end is not None:
        must.append(
            {
                "key": "page_idx",
                "range": {"gte": page_start, "lte": page_end},
            }
        )
    if chunk_types:
        if len(chunk_types) == 1:
            must.append({"key": "chunk_type", "match": chunk_types[0]})
        else:
            must.append({"key": "chunk_type", "any": chunk_types})

    return (
        spec if spec.get("must") or spec.get("should") or spec.get("must_not") else None
    )


def _contains(haystack: Any, needle: str) -> bool:
    if not needle:
        return True
    return needle.casefold() in str(haystack or "").casefold()


def _within_page_range(
    payload: dict[str, Any], page_start: int | None, page_end: int | None
) -> bool:
    if page_start is None and page_end is None:
        return True
    page_idx = payload.get("page_idx")
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
    if chunk_types and str(payload.get("chunk_type", "")) not in chunk_types:
        return False
    heading = payload.get("section_path") or payload.get("heading", "")
    if not _contains(heading, heading_contains):
        return False
    if not _contains(payload.get("authors", ""), authors_contains):
        return False
    if not _contains(payload.get("title", ""), title_contains):
        return False
    if not _contains(payload.get("figure_or_table_label", ""), figure_or_table_label):
        return False
    if not _within_page_range(payload, page_start, page_end):
        return False
    return True


def _format_results(
    results: list[dict[str, Any]],
    source_tool: str,
) -> list[dict[str, Any]]:
    return [
        _payload_to_evidence(doc.get("payload", {}), doc.get("score", 0.0), source_tool)
        for doc in results
    ]


def _visual_key(item: dict[str, Any]) -> tuple[str, str, str]:
    payload = item.get("payload", {})
    pdf_name = str(payload.get("pdf_name", ""))
    page_idx = str(payload.get("page_idx", ""))
    label = str(payload.get("figure_or_table_label", "") or payload.get("img_path", ""))
    return pdf_name, page_idx, label


def _visual_rank(item: dict[str, Any]) -> tuple[float, int, int, int]:
    payload = item.get("payload", {})
    return (
        float(item.get("score", 0.0)),
        1 if payload.get("chunk_type") == "table" else 0,
        1 if payload.get("has_caption") else 0,
        1 if payload.get("has_image") else 0,
    )


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
) -> str:
    """Search paper chunks broadly across text, figures, and tables.

    Use this tool first for most questions about paper content, contributions,
    methods, results, authors, or conclusions.
    """
    metadata_dict = _build_structured_filter(
        filter_metadata,
        pdf_name=pdf_name,
        page_idx=page_idx,
        chunk_types=chunk_types,
        page_start=page_start,
        page_end=page_end,
    )

    try:
        results = vector_store.search_similar(
            query,
            top_k=max(top_k * 3, top_k),
            filter_metadata=metadata_dict,
            candidate_k=max(top_k * 8, 24),
        )
    except Exception as exc:
        logger.error("Vector store search failed: %s", exc)
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
    return _results_json(query, "search_papers", formatted)


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
) -> str:
    """Search specifically for figure and table evidence relevant to a question.

    Prefer this tool when the question mentions figures, tables, experiments,
    ablations, plots, charts, or performance comparisons.
    """
    combined: list[dict[str, Any]] = []
    seen_ids: set[tuple[str, str, str]] = set()

    visual_chunk_types = chunk_types or ["table", "image"]
    visual_query = query
    if (
        figure_or_table_label
        and figure_or_table_label.casefold() not in query.casefold()
    ):
        visual_query = f"{query} {figure_or_table_label}"

    for chunk_type in visual_chunk_types:
        filter_metadata = _build_structured_filter(
            "{}",
            pdf_name=pdf_name,
            page_idx=page_idx,
            chunk_types=[chunk_type],
            page_start=page_start,
            page_end=page_end,
        )
        try:
            results = vector_store.search_similar(
                visual_query,
                top_k=max(4, top_k * 3),
                filter_metadata=filter_metadata,
                score_threshold=0.0,
                candidate_k=max(top_k * 10, 20),
            )
        except Exception as exc:
            logger.error("Visual search failed for %s: %s", chunk_type, exc)
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
            evidence = _payload_to_evidence(
                doc.get("payload", {}),
                doc.get("score", 0.0),
                "search_visuals",
            )
            combined.append(evidence)

    combined.sort(
        key=lambda item: (
            float(item.get("score", 0.0)),
            1 if item.get("chunk_type") == "table" else 0,
            1 if item.get("has_caption") else 0,
        ),
        reverse=True,
    )
    return _results_json(visual_query, "search_visuals", combined[:top_k])


@tool("get_page_context", args_schema=PageContextInput)
def get_page_context(pdf_name: str, page_idx: int, heading: str = "") -> str:
    """Fetch all chunk types from a specific paper page for local context expansion.

    Use this after a search tool identifies a promising page and you want nearby
    context from the same page or section.
    """
    try:
        results = vector_store.fetch_by_metadata(
            {"pdf_name": pdf_name, "page_idx": page_idx},
            limit=20,
        )
    except Exception as exc:
        logger.error("Page-context fetch failed: %s", exc)
        return _results_json(f"{pdf_name}:{page_idx}", "get_page_context", [])

    formatted: list[dict[str, Any]] = []
    for doc in results:
        payload = doc.get("payload", {})
        payload_heading = str(payload.get("heading", ""))
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


AGENT_TOOLS: list[BaseTool] = [
    search_papers,
    search_visuals,
    get_page_context,
]
TOOL_REGISTRY: dict[str, BaseTool] = {tool.name: tool for tool in AGENT_TOOLS}
