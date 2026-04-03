import threading
from typing import Any

import json

from collections.abc import Iterator

from langchain_core.messages import (  # pyright: ignore[reportMissingImports]
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI  # pyright: ignore[reportMissingImports]

from config.settings import config
from src.agent.tooling import AGENT_TOOLS, TOOL_REGISTRY  # pyright: ignore[reportMissingImports]
from src.utils.resilience import call_with_circuit_breaker  # pyright: ignore[reportMissingImports]

_llm: ChatOpenAI | None = None
_model_with_tools: Any | None = None
_llm_lock = threading.Lock()

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
    response = call_with_circuit_breaker(
        get_model_with_tools().invoke,
        [SystemMessage(content=_SYSTEM_PROMPT)] + messages,
    )
    if not isinstance(response, AIMessage):
        raise TypeError(f"Expected AIMessage, got {type(response)!r}")
    return response


def stream_final_answer(messages: list[BaseMessage]) -> Iterator[str]:
    """
    流式输出最终答案。

    Args:
        messages: 消息列表（包含历史和当前对话）

    Yields:
        答案的每个 token
    """
    prompt_messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        *messages,
        SystemMessage(content=_FINAL_ANSWER_PROMPT),
    ]

    stream_iter = call_with_circuit_breaker(get_llm().stream, prompt_messages)
    for chunk in stream_iter:
        if not isinstance(chunk, AIMessageChunk):
            continue
        token = chunk.content if isinstance(chunk.content, str) else ""
        if token:
            yield token


def _build_llm() -> ChatOpenAI:
    client_kwargs: dict[str, Any] = {}
    try:
        import httpx  # pyright: ignore[reportMissingImports]

        client_kwargs["http_client"] = httpx.Client(
            timeout=config.LLM_TIMEOUT_SECONDS,
            limits=httpx.Limits(
                max_keepalive_connections=config.LLM_HTTP_KEEPALIVE_CONNECTIONS,
                max_connections=config.LLM_HTTP_MAX_CONNECTIONS,
            ),
        )
    except Exception:
        client_kwargs = {}

    return ChatOpenAI(
        openai_api_base=config.OPENAI_API_BASE,
        openai_api_key=config.OPENAI_API_KEY,
        model_name=config.LLM_MODEL,
        temperature=1.0,
        timeout=config.LLM_TIMEOUT_SECONDS,
        max_retries=config.LLM_MAX_RETRIES,
        **client_kwargs,
    )


def get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        with _llm_lock:
            if _llm is None:
                _llm = _build_llm()
    return _llm


def get_model_with_tools() -> Any:
    global _llm
    global _model_with_tools
    if _model_with_tools is None:
        with _llm_lock:
            if _model_with_tools is None:
                llm = _llm
                if llm is None:
                    llm = _build_llm()
                    _llm = llm
                _model_with_tools = llm.bind_tools(AGENT_TOOLS)
    return _model_with_tools


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
            artifact = None
        else:
            result = tool.invoke(tool_args)
            if isinstance(result, dict):
                content = json.dumps(result, ensure_ascii=False)
                artifact = result
            else:
                content = str(result)
                artifact = None

        tool_messages.append(
            ToolMessage(
                content=content, tool_call_id=tool_call_id, name=name, artifact=artifact
            )
        )

    return tool_messages


def _tool_event_kind(tool_name: str) -> str:
    mapping = {
        "search_papers": "paper_search",
        "search_visuals": "visual_search",
        "get_page_context": "page_context",
    }
    return mapping.get(tool_name, "tool")


def _extract_visual_evidence(message: Any) -> list[dict[str, Any]]:
    payload = getattr(message, "artifact", None)
    if payload is None:
        content = getattr(message, "content", message)
        if not isinstance(content, str):
            return []
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, TypeError, ValueError):
            return []

    if not isinstance(payload, dict):
        return []

    results = payload.get("results", [])
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


def _summarize_tool_payload(message: Any) -> dict[str, Any]:
    """Extract counts, pages, and chunk-type stats from a tool payload."""
    summary = {
        "count": 0,
        "pages": [],
        "chunk_types": {},
        "pdf_names": [],
    }

    payload = getattr(message, "artifact", None)
    if payload is None:
        content = getattr(message, "content", message)
        if not isinstance(content, str):
            return summary
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, TypeError, ValueError):
            return summary

    if not isinstance(payload, dict):
        return summary

    results = payload.get("results", [])
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


from src.agent.langgraph_agent import agent_app  # noqa: E402
from src.agent.evidence_builder import (  # noqa: E402
    build_structured_provenance,
    collect_evidence,
    enrich_evidence,
)


def run_agent_loop_events(
    question: str,
    history: list[BaseMessage] | None = None,
) -> Iterator[dict[str, Any]]:
    """
    执行 Agent 循环并生成结构化事件。

    Args:
        question: 用户问题
        history: 历史消息列表，用于多轮对话上下文

    Yields:
        结构化事件字典
    """
    # 构建消息列表：历史消息 + 当前问题
    messages = list(history) if history else []
    messages.append(HumanMessage(content=question))

    current_state = {
        "messages": messages,
        "question": question,
        "attached_visuals": set(),
        "iteration_count": 0,
    }

    last_step = 0
    processed_msg_ids = set()
    all_tool_messages: list[ToolMessage] = []

    # We iterate over the stream_mode="values" to catch each state update
    last_summary: dict[str, Any] = {
        "count": 0,
        "pages": [],
        "chunk_types": {},
        "pdf_names": [],
    }
    final_event: dict[str, Any] | None = None

    for event in agent_app.stream(current_state, stream_mode="values"):
        final_event = event
        messages = event.get("messages", [])
        if len(messages) <= 1:
            continue

        last_message = messages[-1]
        step = event.get("iteration_count", 0)

        # When an AIMessage is produced
        if isinstance(last_message, AIMessage):
            msg_id = (
                getattr(last_message, "id", None)
                or f"ai_{hash(last_message.content)}_{step}"
            )
            if msg_id not in processed_msg_ids:
                processed_msg_ids.add(msg_id)
                # If step incremented, it's a new reasoning phase
                if step > last_step:
                    yield {
                        "type": "agent_status",
                        "phase": "thinking",
                        "step": step,
                        "text": "Inspecting the question and deciding the next tool call",
                    }
                    last_step = step

                # If the AIMessage contains tool calls, we yield them
                if last_message.tool_calls:
                    for tool_call in last_message.tool_calls:
                        yield {
                            "type": "tool_call",
                            "kind": _tool_event_kind(tool_call.get("name", "tool")),
                            "tool": tool_call.get("name", "tool"),
                            "args": tool_call.get("args", {}),
                            "step": step,
                        }

        # When ToolMessages are produced, we are after the tools node
        elif isinstance(last_message, ToolMessage) or (
            isinstance(last_message, HumanMessage) and len(messages) > 2
        ):
            tool_msgs = []
            vis_msg = None
            for msg in reversed(messages):
                if isinstance(msg, AIMessage):
                    break
                if isinstance(msg, ToolMessage):
                    tool_msgs.append(msg)
                elif isinstance(msg, HumanMessage):
                    vis_msg = msg

            tool_msgs.reverse()

            for tool_message in tool_msgs:
                msg_id = (
                    getattr(tool_message, "id", None)
                    or f"tool_{tool_message.tool_call_id}"
                )
                if msg_id not in processed_msg_ids:
                    processed_msg_ids.add(msg_id)
                    all_tool_messages.append(tool_message)
                    summary = _summarize_tool_payload(tool_message)
                    last_summary = summary
                    kind = _tool_event_kind(tool_message.name or "tool")

                    yield {
                        "type": "tool_result",
                        "kind": kind,
                        "tool": tool_message.name or "tool",
                        "count": summary.get("count", 0),
                        "pages": summary.get("pages", []),
                        "chunk_types": summary.get("chunk_types", {}),
                        "step": step,
                    }
                    yield {
                        "type": "agent_observation",
                        "kind": kind,
                        "tool": tool_message.name or "tool",
                        "step": step,
                        "text": _tool_observation_text(kind, summary),
                    }

            if vis_msg is not None:
                msg_id = (
                    getattr(vis_msg, "id", None)
                    or f"vis_{hash(str(vis_msg.content))}_{step}"
                )
                if msg_id not in processed_msg_ids:
                    processed_msg_ids.add(msg_id)
                    # Calculate visuals from the content block
                    content_blocks = (
                        vis_msg.content if isinstance(vis_msg.content, list) else []
                    )
                    img_count = (len(content_blocks) - 1) // 2 if content_blocks else 0
                    yield {
                        "type": "agent_visual_context",
                        "step": step,
                        "count": img_count,
                        "pages": last_summary.get("pages", []),
                    }

    # Stream final answer after the graph reaches END
    # The stream already finishes and gives us the final state in the last `event`
    if final_event is None:
        return
    final_messages = final_event.get("messages", [])
    final_step = final_event.get("iteration_count", 0)

    if final_step >= config.AGENT_MAX_ITERATIONS:
        yield {
            "type": "agent_status",
            "phase": "max_iterations",
            "step": config.AGENT_MAX_ITERATIONS,
            "text": "Reached agent iteration limit; answering from current evidence",
        }
    else:
        yield {
            "type": "agent_status",
            "phase": "done",
            "step": final_step,
            "text": "Tool use complete; streaming final answer",
        }

    # Build structured provenance from collected evidence
    evidence = collect_evidence(all_tool_messages)
    enriched = enrich_evidence(evidence)
    provenance = build_structured_provenance(enriched)

    yield {"type": "answer_started"}
    for token in stream_final_answer(final_messages):
        yield {"type": "answer_token", "text": token}
    yield {"type": "answer_done", "sources": provenance}


def stream_answer_events(
    question: str,
    history: list[BaseMessage] | None = None,
) -> Iterator[dict[str, Any]]:
    """
    执行 Agent 并流式返回事件。

    Args:
        question: 用户问题
        history: 历史消息列表

    Yields:
        结构化事件字典
    """
    yield from run_agent_loop_events(question, history)
