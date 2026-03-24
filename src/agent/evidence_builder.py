from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from src.rag.vector_store import vector_store
from src.utils.logger import get_logger

logger = get_logger(__name__)

MAX_TEXT_EVIDENCE_CHARS = 2200
MAX_SUPPORT_TEXT_CHARS = 900
MAX_FINAL_EVIDENCE = 8


def _coerce_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "\n".join(part for part in parts if part)
    return str(content)


def _parse_tool_payload(message: ToolMessage) -> list[dict[str, Any]]:
    payload = getattr(message, "artifact", None)
    
    if payload is None and isinstance(message.content, dict):
        payload = message.content

    if not isinstance(payload, dict):
        return []

    results = payload.get("results")
    if not isinstance(results, list):
        return []

    return [item for item in results if isinstance(item, dict)]


def collect_evidence(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for message in messages:
        if not isinstance(message, ToolMessage):
            continue

        for item in _parse_tool_payload(message):
            evidence_id = str(item.get("evidence_id", ""))
            if evidence_id and evidence_id in seen_ids:
                continue
            if evidence_id:
                seen_ids.add(evidence_id)
            evidence.append(item)

    evidence.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return evidence


def latest_user_question(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return _coerce_text(message.content).strip()
    return ""


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _page_support_text(
    pdf_name: str,
    page_idx: Any,
    heading: str,
    target_page_chunk_order: int | None = None,
    target_chunk_order: int | None = None,
) -> list[dict[str, str]]:
    if not pdf_name or page_idx == "":
        return []

    try:
        results = vector_store.fetch_by_metadata(
            {"pdf_name": pdf_name, "page_idx": page_idx},
            limit=20,
        )
    except Exception as exc:
        logger.warning(
            "Could not fetch page-level support text for %s page %s: %s",
            pdf_name,
            page_idx,
            exc,
        )
        return []

    text_candidates: list[dict[str, Any]] = []
    seen_texts: set[str] = set()

    sorted_results = sorted(
        results,
        key=lambda result: (
            int(result.get("payload", {}).get("page_chunk_order", 10**9)),
            int(result.get("payload", {}).get("chunk_order", 10**9)),
        ),
    )

    for result in sorted_results:
        payload = result.get("payload", {})
        if payload.get("chunk_type") != "text":
            continue

        mm = payload.get("_multimodal_input") or {}
        text = mm.get("text", "") or payload.get("page_content", "")
        text = text.strip()
        if not text or text in seen_texts:
            continue

        payload_heading = str(payload.get("heading", ""))
        if (
            heading
            and payload_heading
            and heading not in payload_heading
            and payload_heading not in heading
        ):
            continue

        seen_texts.add(text)
        page_chunk_order = payload.get("page_chunk_order")
        chunk_order = payload.get("chunk_order")
        proximity = 10**9
        if isinstance(page_chunk_order, int) and target_page_chunk_order is not None:
            proximity = abs(page_chunk_order - target_page_chunk_order)
        elif isinstance(chunk_order, int) and target_chunk_order is not None:
            proximity = abs(chunk_order - target_chunk_order)

        text_candidates.append(
            {
                "heading": payload_heading,
                "text": _truncate(text, MAX_SUPPORT_TEXT_CHARS),
                "page_chunk_order": page_chunk_order,
                "chunk_order": chunk_order,
                "proximity": proximity,
            }
        )

    text_candidates.sort(
        key=lambda item: (
            item["proximity"],
            int(item.get("page_chunk_order", 10**9)),
            int(item.get("chunk_order", 10**9)),
        )
    )

    support_items: list[dict[str, str]] = []
    for item in text_candidates[:2]:
        support_items.append(
            {
                "heading": item["heading"],
                "text": item["text"],
            }
        )
    return support_items


def enrich_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []

    for item in evidence:
        row = dict(item)
        row["text"] = _truncate(str(row.get("text", "")), MAX_TEXT_EVIDENCE_CHARS)
        if row.get("chunk_type") in {"image", "table"}:
            row["support_texts"] = _page_support_text(
                str(row.get("pdf_name", "")),
                row.get("page_idx", ""),
                str(row.get("heading", "")),
                row.get("page_chunk_order")
                if isinstance(row.get("page_chunk_order"), int)
                else None,
                row.get("chunk_order")
                if isinstance(row.get("chunk_order"), int)
                else None,
            )
        else:
            row["support_texts"] = []
        enriched.append(row)

    return enriched


def route_evidence(
    plan: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Apply an agent-produced final plan with minimal post-processing."""
    answer_mode = str(plan.get("answer_mode", "text-only"))
    focus_pages = {str(page) for page in plan.get("focus_pages", []) if page}
    focus_chunk_types = {
        str(chunk_type)
        for chunk_type in plan.get("focus_chunk_types", [])
        if chunk_type
    }

    scoped_evidence = evidence
    if focus_pages:
        scoped = []
        for item in evidence:
            pdf_name = str(item.get("pdf_name", ""))
            page_idx = item.get("page_idx", "")
            page_key = f"{pdf_name}:{page_idx}" if pdf_name and page_idx != "" else ""
            if page_key in focus_pages:
                scoped.append(item)
        if scoped:
            scoped_evidence = scoped

    if focus_chunk_types:
        prioritized = [
            item
            for item in scoped_evidence
            if item.get("chunk_type") in focus_chunk_types
        ]
        if prioritized:
            scoped_evidence = prioritized

    scoped_evidence = sorted(
        scoped_evidence,
        key=lambda item: (
            -float(item.get("score", 0.0)),
            int(item.get("page_chunk_order", 10**9)),
            int(item.get("chunk_order", 10**9)),
        ),
    )

    routed: list[dict[str, Any]] = []
    for item in scoped_evidence[:MAX_FINAL_EVIDENCE]:
        row = dict(item)
        if answer_mode != "multimodal" and row.get("chunk_type") in {"image", "table"}:
            row["img_path"] = ""
            row["support_texts"] = []
        routed.append(row)

    return answer_mode, routed
