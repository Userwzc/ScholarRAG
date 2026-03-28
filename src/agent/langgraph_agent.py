# pyright: reportMissingImports=false

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from config.settings import config
from src.agent.tooling import AGENT_TOOLS, TOOL_REGISTRY
from src.agent.types import AgentState

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


def call_model(messages: list[BaseMessage]) -> AIMessage:
    response = model_with_tools.invoke(
        [SystemMessage(content=_SYSTEM_PROMPT)] + messages
    )
    if not isinstance(response, AIMessage):
        raise TypeError(f"Expected AIMessage, got {type(response)!r}")
    return response


def execute_tool_calls(ai_message: AIMessage) -> list[ToolMessage]:
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


def _image_path_to_data_url(image_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = "image/jpeg"
    data = Path(image_path).read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


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


def agent_node(state: AgentState) -> AgentState:
    ai_message = call_model(list(state["messages"]))
    return {
        "messages": [ai_message],
        "question": state["question"],
        "attached_visuals": set(state.get("attached_visuals", set())),
        "iteration_count": state.get("iteration_count", 0) + 1,
    }


def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return END

    if state.get("iteration_count", 0) >= config.AGENT_MAX_ITERATIONS:
        return END

    return "tools"


def tools_node(state: AgentState) -> AgentState:
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage):
        return {
            "messages": list(state["messages"]),
            "question": state["question"],
            "attached_visuals": set(state.get("attached_visuals", set())),
            "iteration_count": state.get("iteration_count", 0),
        }

    tool_messages = execute_tool_calls(last_message)

    attached_visuals = set(state.get("attached_visuals", set()))
    new_visuals: list[dict[str, Any]] = []
    for tool_message in tool_messages:
        visual_candidates = _extract_visual_evidence(tool_message)
        for item in visual_candidates:
            img_path = str(item.get("img_path", "")).strip()
            if not img_path or img_path in attached_visuals:
                continue
            attached_visuals.add(img_path)
            new_visuals.append(item)

    messages_to_add: list[BaseMessage] = list(tool_messages)
    if new_visuals:
        visual_message = _build_visual_context_message(
            state["question"], new_visuals[:3]
        )
        if visual_message is not None:
            messages_to_add.append(visual_message)

    return {
        "messages": messages_to_add,
        "question": state["question"],
        "attached_visuals": attached_visuals,
        "iteration_count": state.get("iteration_count", 0),
    }


def create_agent_app() -> Any:
    workflow = StateGraph(AgentState)

    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tools_node)

    workflow.set_entry_point("agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            END: END,
        },
    )
    workflow.add_edge("tools", "agent")

    return workflow.compile()


agent_app = create_agent_app()
