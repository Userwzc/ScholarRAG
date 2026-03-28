# pyright: reportMissingImports=false

import importlib


def test_stream_output_writes_stdout(capsys) -> None:
    from src.utils.stream_output import stream_output

    stream_output("hello", end="")
    captured = capsys.readouterr()
    assert captured.out == "hello"


def test_log_status_uses_logger_info(monkeypatch) -> None:
    stream_utils = importlib.import_module("src.utils.stream_output")

    calls: list[str] = []

    class _FakeLogger:
        def info(self, msg: str) -> None:
            calls.append(msg)

    monkeypatch.setattr(stream_utils, "logger", _FakeLogger())
    stream_utils.log_status("status-message")

    assert calls == ["status-message"]


def test_query_agent_status_goes_to_logger_and_token_to_stdout(monkeypatch, capsys) -> None:
    cli_main = importlib.import_module("main")

    events = [
        {"type": "agent_status", "phase": "thinking", "step": 1, "text": "start"},
        {"type": "answer_started"},
        {"type": "answer_token", "text": "A"},
        {"type": "answer_token", "text": "B"},
    ]

    def _fake_stream(_question: str):
        for evt in events:
            yield evt

    class _FakeLogger:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def info(self, msg: str) -> None:
            self.messages.append(msg)

        def debug(self, _fmt: str, *_args) -> None:
            return

        def warning(self, _fmt: str, *_args) -> None:
            return

        def error(self, _fmt: str, *_args, **_kwargs) -> None:
            return

    fake_status_logger = _FakeLogger()

    monkeypatch.setattr("src.utils.stream_output.logger", fake_status_logger)
    monkeypatch.setattr("src.agent.graph.stream_answer_events", _fake_stream)

    cli_main.query_agent("test")

    captured = capsys.readouterr()
    assert "AB" in captured.out
    assert any("[agent:thinking:1] start" in msg for msg in fake_status_logger.messages)
