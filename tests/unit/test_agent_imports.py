def test_import_stream_answer_events() -> None:
    from src.agent.graph import stream_answer_events

    assert callable(stream_answer_events)


def test_import_agent_app() -> None:
    from src.agent.langgraph_agent import agent_app

    assert agent_app is not None
