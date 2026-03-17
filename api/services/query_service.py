import json
from typing import Any, Generator, Iterator


def stream_query(question: str) -> Generator[str, None, None]:
    from src.agent.graph import stream_answer_events

    for event in stream_answer_events(question):
        event_type = event.get("type", "")

        if event_type == "agent_status":
            yield f"event: status\ndata: {json.dumps(event)}\n\n"
        elif event_type == "tool_call":
            yield f"event: tool_call\ndata: {json.dumps(event)}\n\n"
        elif event_type == "tool_result":
            yield f"event: tool_result\ndata: {json.dumps(event)}\n\n"
        elif event_type == "agent_observation":
            yield f"event: agent_observation\ndata: {json.dumps(event)}\n\n"
        elif event_type == "agent_visual_context":
            yield f"event: agent_visual_context\ndata: {json.dumps(event)}\n\n"
        elif event_type == "answer_started":
            yield f"event: answer_started\ndata: {json.dumps(event)}\n\n"
        elif event_type == "answer_token":
            yield f"event: answer_token\ndata: {json.dumps(event)}\n\n"
        elif event_type == "answer_done":
            yield f"event: answer_done\ndata: {json.dumps(event)}\n\n"
