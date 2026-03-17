from typing import TypedDict, Annotated, Sequence, Any
import operator
from langchain_core.messages import BaseMessage, AnyMessage, HumanMessage, AIMessage, ToolMessage

from langgraph.graph import StateGraph, END

from config.settings import config
from src.agent.graph import (
    call_model, 
    stream_final_answer, 
    execute_tool_calls,
    _tool_event_kind,
    _summarize_tool_payload,
    _tool_observation_text,
    _extract_visual_evidence,
    _build_visual_context_message
)

class AgentGraphState(TypedDict):
    messages: Annotated[Sequence[AnyMessage], operator.add]
    question: str
    attached_visuals: set[str]
    iteration_count: int

def agent_node(state: AgentGraphState):
    """The thinking node."""
    ai_message = call_model(state["messages"])
    return {
        "messages": [ai_message],
        "iteration_count": state.get("iteration_count", 0) + 1
    }

def should_continue(state: AgentGraphState) -> str:
    """Determine the next node."""
    last_message = state["messages"][-1]
    
    # If there are no tool calls, finish reasoning and go to generate answer
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return END

    if state.get("iteration_count", 0) >= config.AGENT_MAX_ITERATIONS:
        return END
        
    return "tools"

def tools_node(state: AgentGraphState):
    """Execute tools and inject visual context if any."""
    last_message = state["messages"][-1]
    
    # We only reach here if the last message is an AIMessage with tool calls
    tool_messages = execute_tool_calls(last_message)
    
    # Check for visuals
    attached_visuals = set(state.get("attached_visuals", set()))
    new_visuals = []
    
    for tool_message in tool_messages:
        visual_candidates = _extract_visual_evidence(tool_message)
        for item in visual_candidates:
            img_path = str(item.get("img_path", "")).strip()
            if not img_path or img_path in attached_visuals:
                continue
            attached_visuals.add(img_path)
            new_visuals.append(item)
            
    # If we found new visuals, build a context message and append it
    messages_to_add = list(tool_messages)
    if new_visuals:
        visual_message = _build_visual_context_message(state["question"], new_visuals[:3])
        if visual_message is not None:
            messages_to_add.append(visual_message)
            
    return {
        "messages": messages_to_add,
        "attached_visuals": attached_visuals
    }

def create_agent_app():
    workflow = StateGraph(AgentGraphState)

    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tools_node)

    workflow.set_entry_point("agent")
    
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            END: END
        }
    )
    workflow.add_edge("tools", "agent")

    return workflow.compile()

agent_app = create_agent_app()
