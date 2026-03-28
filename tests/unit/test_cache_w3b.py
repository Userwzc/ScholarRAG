from __future__ import annotations

import time
from typing import Any

import pytest

from src.agent import tools
from src.ingest.mineru_parser import MinerUParser
from src.utils.cache import QueryCache, clear_tokenizer_cache


def _minimal_middle_data() -> dict[str, Any]:
    return {
        "pdf_info": [
            {
                "page_idx": 0,
                "discarded_blocks": [],
                "para_blocks": [
                    {
                        "type": "title",
                        "lines": [{"spans": [{"content": "Demo Paper"}]}],
                    },
                    {
                        "type": "title",
                        "lines": [{"spans": [{"content": "Abstract"}]}],
                    },
                    {
                        "type": "text",
                        "lines": [
                            {
                                "spans": [
                                    {
                                        "content": (
                                            "This is a short paragraph for tokenizer counting."
                                        )
                                    }
                                ]
                            }
                        ],
                    },
                ],
            }
        ]
    }


def test_tokenizer_initialized_once_across_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_tokenizer_cache()
    init_counter = {"count": 0}

    class _FakeEncoding:
        def encode(self, text: str) -> list[str]:
            return text.split()

    def _fake_get_encoding(name: str) -> _FakeEncoding:  # noqa: ARG001
        init_counter["count"] += 1
        return _FakeEncoding()

    monkeypatch.setattr("src.utils.cache.tiktoken.get_encoding", _fake_get_encoding)

    parser = MinerUParser(output_dir="/tmp/scholarrag_test_output", backend="pipeline")
    parser.process_middle_json(_minimal_middle_data(), max_chunk_size=50)
    parser.process_middle_json(_minimal_middle_data(), max_chunk_size=50)

    assert init_counter["count"] == 1


def test_query_cache_hit_avoids_second_vector_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StubService:
        def __init__(self) -> None:
            self.calls = 0

        def search_papers(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:  # noqa: ARG002
            self.calls += 1
            return [
                {
                    "payload": {
                        "page_content": "cached text",
                        "metadata": {
                            "title": "Cache Demo",
                            "pdf_name": "cache_demo",
                            "authors": "Tester",
                            "page_idx": 1,
                            "chunk_type": "text",
                            "heading": "Intro",
                        },
                    },
                    "score": 0.95,
                }
            ]

    stub_store = _StubService()
    monkeypatch.setattr(tools, "get_retrieval_service", lambda: stub_store)
    monkeypatch.setattr(tools, "QUERY_CACHE", QueryCache(ttl=300))

    result_1 = tools._search_papers_impl(query="what is cache")
    result_2 = tools._search_papers_impl(query="what is cache")

    assert stub_store.calls == 1
    assert result_1["results"] == result_2["results"]


def test_query_cache_hit_latency_under_10ms(monkeypatch: pytest.MonkeyPatch) -> None:
    class _StubService:
        def search_papers(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:  # noqa: ARG002
            time.sleep(0.05)
            return [
                {
                    "payload": {
                        "page_content": "latency text",
                        "metadata": {
                            "title": "Latency Demo",
                            "pdf_name": "latency_demo",
                            "authors": "Tester",
                            "page_idx": 3,
                            "chunk_type": "text",
                            "heading": "Results",
                        },
                    },
                    "score": 0.9,
                }
            ]

    monkeypatch.setattr(tools, "get_retrieval_service", lambda: _StubService())
    monkeypatch.setattr(tools, "QUERY_CACHE", QueryCache(ttl=300))

    tools._search_papers_impl(query="latency")
    start = time.perf_counter()
    tools._search_papers_impl(query="latency")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < 10


def test_query_cache_ttl_expiration_triggers_requery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StubService:
        def __init__(self) -> None:
            self.calls = 0

        def search_papers(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:  # noqa: ARG002
            self.calls += 1
            return [
                {
                    "payload": {
                        "page_content": "ttl text",
                        "metadata": {
                            "title": "TTL Demo",
                            "pdf_name": "ttl_demo",
                            "authors": "Tester",
                            "page_idx": 2,
                            "chunk_type": "text",
                            "heading": "Method",
                        },
                    },
                    "score": 0.91,
                }
            ]

    stub_store = _StubService()
    monkeypatch.setattr(tools, "get_retrieval_service", lambda: stub_store)
    monkeypatch.setattr(tools, "QUERY_CACHE", QueryCache(ttl=1))

    tools._search_papers_impl(query="ttl-check")
    time.sleep(1.2)
    tools._search_papers_impl(query="ttl-check")

    assert stub_store.calls == 2
