from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Check if torch is available - skip all tests if not
try:
    import torch  # noqa: F401

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not TORCH_AVAILABLE,
    reason="torch not installed - skipping vector store optimization tests",
)


# Only import if torch is available
if TORCH_AVAILABLE:
    from src.rag.vector_store import MultimodalQdrantStore


def _build_store_for_similarity_search() -> "MultimodalQdrantStore":
    store = object.__new__(MultimodalQdrantStore)
    store.collection_name = "papers"
    store.content_payload_key = "page_content"
    store.metadata_payload_key = "metadata"
    store._client = MagicMock()
    return store


def _build_store_for_add_multimodal() -> "MultimodalQdrantStore":
    from src.rag import vector_store as vector_store_module

    store = object.__new__(MultimodalQdrantStore)
    store.collection_name = "papers"
    store.content_payload_key = "page_content"
    store.metadata_payload_key = "metadata"
    store.MULTIMODAL_KEY = "_multimodal_input"
    store.vector_name = "dense"
    store.retrieval_mode = vector_store_module.RetrievalMode.DENSE
    store._client = MagicMock()
    store._embeddings = MagicMock()
    store._embeddings.embed_documents.side_effect = lambda batch: [
        [0.1, 0.2] for _ in batch
    ]
    return store


def test_similarity_search_no_n_plus_1() -> None:
    store = _build_store_for_similarity_search()

    docs = [
        SimpleNamespace(
            page_content=f"chunk-{idx}",
            metadata={"_id": f"pid-{idx}", "pdf_name": "paper", "page_idx": idx},
        )
        for idx in range(10)
    ]
    store.similarity_search_with_score = MagicMock(
        return_value=[(doc, 0.9) for doc in docs]
    )

    _ = store.similarity_search("query", k=10)

    assert store.similarity_search_with_score.call_count == 1
    assert store._client.retrieve.call_count <= 1


def test_add_multimodal_uses_config_embedding_batch_size(monkeypatch) -> None:
    from src.rag import vector_store as vector_store_module

    store = _build_store_for_add_multimodal()
    monkeypatch.setattr(vector_store_module.config, "EMBEDDING_BATCH_SIZE", 32)

    inputs = [{"text": f"chunk-{i}"} for i in range(33)]
    metadatas = [{"pdf_name": "paper", "page_idx": i} for i in range(33)]

    _ = store.add_multimodal(inputs, metadatas, batch_size=None)

    batch_sizes = [
        len(call.args[0]) for call in store._embeddings.embed_documents.call_args_list
    ]
    assert batch_sizes == [32, 1]
    assert store._client.upsert.call_count == 2


def test_add_multimodal_explicit_batch_size_overrides_config(monkeypatch) -> None:
    from src.rag import vector_store as vector_store_module

    store = _build_store_for_add_multimodal()
    monkeypatch.setattr(vector_store_module.config, "EMBEDDING_BATCH_SIZE", 32)

    inputs = [{"text": f"chunk-{i}"} for i in range(17)]
    metadatas = [{"pdf_name": "paper", "page_idx": i} for i in range(17)]

    _ = store.add_multimodal(inputs, metadatas, batch_size=8)

    batch_sizes = [
        len(call.args[0]) for call in store._embeddings.embed_documents.call_args_list
    ]
    assert batch_sizes == [8, 8, 1]


def test_qdrant_client_singleton_reuse(monkeypatch) -> None:
    from src.rag import vector_store as vector_store_module

    client_instance = object()
    client_cls = MagicMock(return_value=client_instance)

    monkeypatch.setattr(vector_store_module, "_qdrant_client", None)
    monkeypatch.setattr(vector_store_module, "QdrantClient", client_cls)

    first = vector_store_module._get_qdrant_client()
    second = vector_store_module._get_qdrant_client()

    assert first is second
    assert client_cls.call_count == 1


def test_graph_llm_reuse(monkeypatch) -> None:
    import sys

    fake_tooling_module = type(sys)("src.agent.tooling")
    setattr(fake_tooling_module, "AGENT_TOOLS", [])
    setattr(fake_tooling_module, "TOOL_REGISTRY", {})
    monkeypatch.setitem(sys.modules, "src.agent.tooling", fake_tooling_module)

    fake_resilience_module = type(sys)("src.utils.resilience")
    setattr(
        fake_resilience_module,
        "call_with_circuit_breaker",
        lambda fn, *a, **k: fn(*a, **k),
    )
    monkeypatch.setitem(sys.modules, "src.utils.resilience", fake_resilience_module)

    fake_langgraph_agent = type(sys)("src.agent.langgraph_agent")
    setattr(fake_langgraph_agent, "agent_app", MagicMock())
    monkeypatch.setitem(sys.modules, "src.agent.langgraph_agent", fake_langgraph_agent)

    fake_evidence_builder = type(sys)("src.agent.evidence_builder")
    setattr(fake_evidence_builder, "build_structured_provenance", lambda _: {})
    setattr(fake_evidence_builder, "collect_evidence", lambda _: [])
    setattr(fake_evidence_builder, "enrich_evidence", lambda x: x)
    monkeypatch.setitem(
        sys.modules, "src.agent.evidence_builder", fake_evidence_builder
    )

    graph_module = importlib.import_module("src.agent.graph")

    bound_model = object()
    llm_instance = MagicMock()
    llm_instance.bind_tools.return_value = bound_model
    chat_openai_cls = MagicMock(return_value=llm_instance)

    monkeypatch.setattr(graph_module, "_llm", None)
    monkeypatch.setattr(graph_module, "_model_with_tools", None)
    monkeypatch.setattr(graph_module, "ChatOpenAI", chat_openai_cls)

    first = graph_module.get_model_with_tools()
    second = graph_module.get_model_with_tools()

    assert first is second
    assert chat_openai_cls.call_count == 1
    assert llm_instance.bind_tools.call_count == 1


def test_embedding_batch_size_config_default_and_override(monkeypatch) -> None:
    import config.settings as settings_module

    monkeypatch.delenv("EMBEDDING_BATCH_SIZE", raising=False)
    importlib.reload(settings_module)
    assert settings_module.config.EMBEDDING_BATCH_SIZE == 32

    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "48")
    importlib.reload(settings_module)
    assert settings_module.config.EMBEDDING_BATCH_SIZE == 48
