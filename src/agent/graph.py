from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path

from collections.abc import Iterator
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI

from config.settings import config
from src.agent.tools import AGENT_TOOLS, TOOL_REGISTRY

llm = ChatOpenAI(
    openai_api_base=config.OPENAI_API_BASE,
    openai_api_key=config.OPENAI_API_KEY,
    model_name=config.LLM_MODEL,
    temperature=1.0,
)

model_with_tools = llm.bind_tools(AGENT_TOOLS)

_SYSTEM_PROMPT = """\
You are an expert Research AI Assistant with access to academic papers stored in a vector database.

You may decide which tool to use and how many tool calls are needed before answering.

Available tools:
- search_papers: broad semantic search across paper content
- search_visuals: focused search for figures, tables, ablations, and result comparisons
- get_page_context: fetch all chunks from a specific page for local context expansion

Tool-selection rules:
- Always call at least one tool before answering any question about paper content.
- Choose tools dynamically based on the question and the evidence you have already gathered.
- After each tool result, reassess whether you already have enough evidence or whether another tool call would help.
- Retrieved visuals may be attached directly in later turns as multimodal context; inspect them when they are useful.
- When possible, use structured tool fields such as pdf_name, page_idx/page range, chunk_types, heading_contains, title_contains, authors_contains, and figure_or_table_label instead of broad unconstrained searches.
- Use multiple tool calls when useful, but avoid redundant repetition.

Answer rules:
- Base your answer strictly on retrieved evidence.
- If evidence is insufficient, say so clearly.
- Do not narrate your reasoning or your tool-selection process to the user.
- The final answer should be produced after tool use is complete.
- When the evidence is sufficient, stop calling tools and answer the user directly.
"""

_FINAL_ANSWER_PROMPT = """\
Answer the user's question directly based on the conversation and retrieved evidence.

Rules:
- Do not call tools.
- Do not describe your internal reasoning or tool-selection process.
- Base the answer strictly on the retrieved evidence already present in the conversation.
- If the evidence is insufficient, say so clearly.
"""


def call_model(messages: list[BaseMessage]) -> AIMessage:
    """Invoke the tool-calling model with the current message history."""
    response = model_with_tools.invoke(
        [SystemMessage(content=_SYSTEM_PROMPT)] + messages
    )
    if not isinstance(response, AIMessage):
        raise TypeError(f"Expected AIMessage, got {type(response)!r}")
    return response


def stream_final_answer(messages: list[BaseMessage]) -> Iterator[str]:
    """Stream the final answer from the main model without tool calls."""
    prompt_messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        *messages,
        HumanMessage(content=_FINAL_ANSWER_PROMPT),
    ]

    for chunk in llm.stream(prompt_messages):
        if not isinstance(chunk, AIMessageChunk):
            continue
        token = chunk.content if isinstance(chunk.content, str) else ""
        if token:
            yield token


def execute_tool_calls(ai_message: AIMessage) -> list[ToolMessage]:
    """Execute all requested tool calls and return ToolMessages."""
    tool_messages: list[ToolMessage] = []

    for tool_call in ai_message.tool_calls:
        name = tool_call.get("name", "")
        tool_args = tool_call.get("args", {})
        tool_call_id = tool_call.get("id", "")

        tool = TOOL_REGISTRY.get(name)
        if tool is None:
            content = f"Unknown tool: {name}"
        else:
            content = tool.invoke(tool_args)

        tool_messages.append(
            ToolMessage(content=content, tool_call_id=tool_call_id, name=name)
        )

    return tool_messages


def _tool_event_kind(tool_name: str) -> str:
    mapping = {
        "search_papers": "paper_search",
        "search_visuals": "visual_search",
        "get_page_context": "page_context",
    }
    return mapping.get(tool_name, "tool")


def _image_path_to_data_url(image_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = "image/jpeg"
    data = Path(image_path).read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_visual_evidence(content: Any) -> list[dict[str, Any]]:
    if not isinstance(content, str):
        return []

    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []

    results = parsed.get("results", [])
    if not isinstance(results, list):
        return []

    visuals: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        img_path = str(item.get("img_path", "")).strip()
        if not img_path:
            continue
        visuals.append(item)
    return visuals


def _build_visual_context_message(
    question: str,
    visuals: list[dict[str, Any]],
) -> HumanMessage | None:
    if not visuals:
        return None

    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "Retrieved visual context for the current question. "
                "Inspect these images only if they help answer the question.\n"
                f"Question: {question}"
            ),
        }
    ]

    for index, item in enumerate(visuals, start=1):
        img_path = str(item.get("img_path", "")).strip()
        if not img_path:
            continue
        try:
            data_url = _image_path_to_data_url(img_path)
        except Exception:
            continue

        pdf_name = str(item.get("pdf_name", ""))
        page_idx = item.get("page_idx", "")
        heading = str(item.get("heading", ""))
        caption = str(item.get("caption", ""))
        chunk_type = str(item.get("chunk_type", "image"))

        lines = [f"Visual {index}"]
        if pdf_name:
            lines.append(f"Paper: {pdf_name}.pdf")
        if page_idx != "":
            lines.append(f"Page: {page_idx}")
        lines.append(f"Type: {chunk_type}")
        if heading:
            lines.append(f"Heading: {heading}")
        if caption:
            lines.append(f"Caption: {caption}")

        content.append({"type": "text", "text": "\n".join(lines)})
        content.append({"type": "image_url", "image_url": {"url": data_url}})

    if len(content) == 1:
        return None
    return HumanMessage(content=content)


def _summarize_tool_payload(content: Any) -> dict[str, Any]:
    """Extract counts, pages, and chunk-type stats from a tool payload."""
    summary = {
        "count": 0,
        "pages": [],
        "chunk_types": {},
        "pdf_names": [],
    }
    if not isinstance(content, str):
        return summary

    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError, ValueError):
        return summary

    results = parsed.get("results", [])
    if not isinstance(results, list):
        return summary

    pages: set[str] = set()
    pdf_names: set[str] = set()
    chunk_types: dict[str, int] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        pdf_name = str(item.get("pdf_name", ""))
        page_idx = item.get("page_idx", "")
        if pdf_name:
            pdf_names.add(pdf_name)
        if pdf_name and page_idx != "":
            pages.add(f"{pdf_name}:{page_idx}")
        chunk_type = str(item.get("chunk_type", "text"))
        chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1

    summary["count"] = len(results)
    summary["pages"] = sorted(pages)
    summary["chunk_types"] = chunk_types
    summary["pdf_names"] = sorted(pdf_names)
    return summary


def _tool_observation_text(kind: str, summary: dict[str, Any]) -> str:
    count = int(summary.get("count", 0))
    pages = summary.get("pages", [])[:3]
    chunk_types = summary.get("chunk_types", {})

    if kind == "paper_search":
        if count == 0:
            return "Paper search found no relevant chunks"
        page_text = f" on {', '.join(pages)}" if pages else ""
        return f"Paper search found {count} chunk(s){page_text}"

    if kind == "visual_search":
        tables = int(chunk_types.get("table", 0))
        images = int(chunk_types.get("image", 0))
        page_text = f" on {', '.join(pages)}" if pages else ""
        return (
            f"Visual search found {count} item(s) "
            f"({tables} table(s), {images} image(s)){page_text}"
        )

    if kind == "page_context":
        page_text = pages[0] if pages else "the requested page"
        return f"Page context fetched {count} local chunk(s) from {page_text}"

    return f"Tool returned {count} item(s)"


def run_agent_loop_events(
    question: str,
) -> Iterator[dict[str, Any]]:
    """Run an autonomous tool-using agent loop and yield structured events."""
    messages: list[BaseMessage] = [HumanMessage(content=question)]
    attached_visuals: set[str] = set()

    for step in range(1, config.AGENT_MAX_ITERATIONS + 1):
        yield {
            "type": "agent_status",
            "phase": "thinking",
            "step": step,
            "text": "Inspecting the question and deciding the next tool call",
        }

        ai_message = call_model(messages)

        if not ai_message.tool_calls:
            yield {
                "type": "agent_status",
                "phase": "done",
                "step": step,
                "text": "Tool use complete; streaming final answer",
            }
            yield {"type": "answer_started"}
            for token in stream_final_answer(messages):
                yield {"type": "answer_token", "text": token}
            yield {"type": "answer_done"}
            break

        messages.append(ai_message)

        for tool_call in ai_message.tool_calls:
            args = tool_call.get("args", {})
            yield {
                "type": "tool_call",
                "kind": _tool_event_kind(tool_call.get("name", "tool")),
                "tool": tool_call.get("name", "tool"),
                "args": args,
                "step": step,
            }

        tool_messages = execute_tool_calls(ai_message)
        messages.extend(tool_messages)

        for tool_message in tool_messages:
            summary = _summarize_tool_payload(tool_message.content)
            kind = _tool_event_kind(tool_message.name or "tool")

            yield {
                "type": "tool_result",
                "kind": kind,
                "tool": tool_message.name or "tool",
                "count": summary["count"],
                "pages": summary["pages"],
                "chunk_types": summary["chunk_types"],
                "step": step,
            }
            yield {
                "type": "agent_observation",
                "kind": kind,
                "tool": tool_message.name or "tool",
                "step": step,
                "text": _tool_observation_text(kind, summary),
            }

            visual_candidates = _extract_visual_evidence(tool_message.content)
            fresh_visuals = []
            for item in visual_candidates:
                img_path = str(item.get("img_path", "")).strip()
                if not img_path or img_path in attached_visuals:
                    continue
                attached_visuals.add(img_path)
                fresh_visuals.append(item)

            visual_message = _build_visual_context_message(question, fresh_visuals[:3])
            if visual_message is not None:
                messages.append(visual_message)
                yield {
                    "type": "agent_visual_context",
                    "step": step,
                    "count": len(fresh_visuals[:3]),
                    "pages": summary["pages"],
                }
    else:
        yield {
            "type": "agent_status",
            "phase": "max_iterations",
            "step": config.AGENT_MAX_ITERATIONS,
            "text": "Reached agent iteration limit; answering from current evidence",
        }
        yield {"type": "answer_started"}
        for token in stream_final_answer(messages):
            yield {"type": "answer_token", "text": token}
        yield {"type": "answer_done"}


def stream_answer_events(
    question: str,
) -> Iterator[dict[str, Any]]:
    """Run the autonomous agent loop and stream events directly."""
    yield from run_agent_loop_events(question)
