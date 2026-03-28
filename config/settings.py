# pyright: reportMissingImports=false

import os

from dotenv import load_dotenv

# load_dotenv() here provides defaults when this module is imported directly
# (e.g. in tests or notebooks).  In the main CLI, main.py calls
# load_dotenv(override=True) *before* importing this module so that .env
# values take priority over any pre-set system environment variables.
load_dotenv()


def _parse_int_env(name: str, default: int) -> int:
    """Read an integer environment variable; raise ValueError on bad values."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(
            f"Environment variable {name!r} must be an integer, got {raw!r}"
        ) from None


class Config:
    OPENAI_API_BASE: str = os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1")
    # Absence of OPENAI_API_KEY produces an empty string; callers should
    # validate this rather than getting a cryptic auth failure later.
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = _parse_int_env("QDRANT_PORT", 6333)

    # Local Qwen3-VL embedding model path (relative to project root).
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "models/Qwen3-VL-Embedding-2B")
    EMBEDDING_BATCH_SIZE: int = _parse_int_env("EMBEDDING_BATCH_SIZE", 32)

    # LLM served via an OpenAI-compatible API endpoint.
    LLM_MODEL: str = os.getenv("LLM_MODEL", "Pro/moonshotai/Kimi-K2.5")

    # MinerU model source: local | modelscope | huggingface
    MINERU_MODEL_SOURCE: str = os.getenv("MINERU_MODEL_SOURCE", "modelscope")

    # RAG retrieval tuning
    # Number of chunks returned to the LLM by the retriever tool.
    RAG_TOP_K: int = _parse_int_env("RAG_TOP_K", 5)
    # Minimum cosine-similarity score (0–1) to include a chunk in results.
    # Chunks below this threshold are discarded before reaching the LLM.
    # Set to 0.0 to disable threshold filtering.
    SCORE_THRESHOLD: float = float(os.getenv("SCORE_THRESHOLD", "0.3"))

    # Maximum number of agent loop iterations before the graph forcibly stops.
    AGENT_MAX_ITERATIONS: int = _parse_int_env("AGENT_MAX_ITERATIONS", 10)

    # MinerU backend selection: pipeline | hybrid-auto-engine
    MINERU_BACKEND: str = os.getenv("MINERU_BACKEND", "pipeline")

    # PDF storage directory for reader functionality
    PDF_STORAGE_DIR: str = os.getenv("PDF_STORAGE_DIR", "./data/pdfs")

    PARSED_OUTPUT_DIR: str = os.getenv("PARSED_OUTPUT_DIR", "./data/parsed")

    # Hybrid retrieval mode (dense + sparse vectors)
    # When enabled, uses both dense embeddings and BM25 sparse embeddings
    # Requires: pip install fastembed
    ENABLE_HYBRID: bool = os.getenv("ENABLE_HYBRID", "false").lower() == "true"

    # Qdrant collection name for storing paper chunks.
    QDRANT_COLLECTION_NAME: str = os.getenv("QDRANT_COLLECTION_NAME", "papers_rag")
    QDRANT_TIMEOUT_SECONDS: int = _parse_int_env("QDRANT_TIMEOUT_SECONDS", 10)
    QDRANT_HTTP_KEEPALIVE_CONNECTIONS: int = _parse_int_env(
        "QDRANT_HTTP_KEEPALIVE_CONNECTIONS", 20
    )
    QDRANT_HTTP_MAX_CONNECTIONS: int = _parse_int_env(
        "QDRANT_HTTP_MAX_CONNECTIONS", 100
    )

    LLM_TIMEOUT_SECONDS: int = _parse_int_env("LLM_TIMEOUT_SECONDS", 120)
    LLM_HTTP_KEEPALIVE_CONNECTIONS: int = _parse_int_env(
        "LLM_HTTP_KEEPALIVE_CONNECTIONS", 20
    )
    LLM_HTTP_MAX_CONNECTIONS: int = _parse_int_env("LLM_HTTP_MAX_CONNECTIONS", 100)
    LLM_MAX_RETRIES: int = _parse_int_env("LLM_MAX_RETRIES", 2)


config = Config()
