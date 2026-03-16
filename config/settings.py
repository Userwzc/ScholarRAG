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

    # Local Qwen3-VL reranker model path. Set to empty string to disable reranking.
    RERANKER_MODEL: str = os.getenv("RERANKER_MODEL", "")

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


config = Config()
