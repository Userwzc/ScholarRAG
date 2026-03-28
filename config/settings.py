# pyright: reportMissingImports=false

import os
from pathlib import Path

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


def _parse_bool_env(name: str, default: bool) -> bool:
    """Read a boolean environment variable."""
    raw = os.getenv(name, str(default).lower())
    return raw.lower() in ("true", "1", "yes", "on")


def _validate_enum(value: str, valid_values: list[str], name: str) -> str:
    """Validate that a value is one of the allowed enum values."""
    if value not in valid_values:
        raise ValueError(
            f"Environment variable {name!r} must be one of {valid_values!r}, got {value!r}"
        )
    return value


class Config:
    # =============================================================================
    # LLM API 配置
    # =============================================================================
    OPENAI_API_BASE: str = os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1")
    # Absence of OPENAI_API_KEY produces an empty string; callers should
    # validate this rather than getting a cryptic auth failure later.
    # For remote endpoints (not localhost), a non-empty key is required.
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # LLM served via an OpenAI-compatible API endpoint.
    LLM_MODEL: str = os.getenv("LLM_MODEL", "Pro/moonshotai/Kimi-K2.5")

    # =============================================================================
    # 向量数据库配置 (Qdrant)
    # =============================================================================
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = _parse_int_env("QDRANT_PORT", 6333)
    QDRANT_COLLECTION_NAME: str = os.getenv("QDRANT_COLLECTION_NAME", "papers_rag")
    QDRANT_TIMEOUT_SECONDS: int = _parse_int_env("QDRANT_TIMEOUT_SECONDS", 10)
    QDRANT_HTTP_KEEPALIVE_CONNECTIONS: int = _parse_int_env(
        "QDRANT_HTTP_KEEPALIVE_CONNECTIONS", 20
    )
    QDRANT_HTTP_MAX_CONNECTIONS: int = _parse_int_env(
        "QDRANT_HTTP_MAX_CONNECTIONS", 100
    )

    # =============================================================================
    # 嵌入模型配置 (Qwen3-VL)
    # =============================================================================
    # Local Qwen3-VL embedding model path (relative to project root).
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "models/Qwen3-VL-Embedding-2B")
    EMBEDDING_BATCH_SIZE: int = _parse_int_env("EMBEDDING_BATCH_SIZE", 32)

    # =============================================================================
    # PDF 解析配置 (MinerU)
    # =============================================================================
    # MinerU model source: local | modelscope | huggingface
    MINERU_MODEL_SOURCE: str = _validate_enum(
        os.getenv("MINERU_MODEL_SOURCE", "modelscope"),
        ["local", "modelscope", "huggingface"],
        "MINERU_MODEL_SOURCE",
    )

    # MinerU backend selection: pipeline | hybrid-auto-engine
    MINERU_BACKEND: str = _validate_enum(
        os.getenv("MINERU_BACKEND", "pipeline"),
        ["pipeline", "hybrid-auto-engine"],
        "MINERU_BACKEND",
    )

    # =============================================================================
    # RAG 检索配置
    # =============================================================================
    # Number of chunks returned to the LLM by the retriever tool.
    RAG_TOP_K: int = _parse_int_env("RAG_TOP_K", 5)
    # Minimum cosine-similarity score (0–1) to include a chunk in results.
    # Chunks below this threshold are discarded before reaching the LLM.
    # Set to 0.0 to disable threshold filtering.
    SCORE_THRESHOLD: float = float(os.getenv("SCORE_THRESHOLD", "0.3"))

    # Maximum number of agent loop iterations before the graph forcibly stops.
    AGENT_MAX_ITERATIONS: int = _parse_int_env("AGENT_MAX_ITERATIONS", 10)

    # Hybrid retrieval mode (dense + sparse vectors)
    # When enabled, uses both dense embeddings and BM25 sparse embeddings
    # Requires: pip install fastembed
    ENABLE_HYBRID: bool = _parse_bool_env("ENABLE_HYBRID", False)

    # =============================================================================
    # 存储路径配置
    # =============================================================================
    # PDF storage directory for reader functionality
    PDF_STORAGE_DIR: str = os.getenv("PDF_STORAGE_DIR", "./data/pdfs")
    PARSED_OUTPUT_DIR: str = os.getenv("PARSED_OUTPUT_DIR", "./data/parsed")

    # =============================================================================
    # API 服务配置 (FastAPI) - 从 api/config.py 迁移
    # =============================================================================
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = _parse_int_env("API_PORT", 8000)
    API_UPLOAD_DIR: str = os.getenv("API_UPLOAD_DIR", "./data/uploads")

    # =============================================================================
    # 数据库配置 - 从 api/config.py 迁移
    # =============================================================================
    DATABASE_PATH: str = os.getenv(
        "DATABASE_PATH", str(Path(__file__).parent.parent / "data" / "conversations.db")
    )
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", f"sqlite+aiosqlite:///{DATABASE_PATH}"
    )

    # =============================================================================
    # 后台任务配置 - 从 async_upload_service.py 迁移
    # =============================================================================
    # 是否启用数据库任务租约（防止多 worker 重复处理）
    USE_DB_JOB_LEASE: bool = _parse_bool_env("USE_DB_JOB_LEASE", False)
    # 任务租约过期时间（秒）
    JOB_LEASE_TTL_SECONDS: int = _parse_int_env("JOB_LEASE_TTL_SECONDS", 300)
    # 后台执行器类型: thread | process
    EXECUTOR_TYPE: str = _validate_enum(
        os.getenv("EXECUTOR_TYPE", "thread"), ["thread", "process"], "EXECUTOR_TYPE"
    )
    # 后台执行器并行 worker 数
    BACKGROUND_EXECUTOR_WORKERS: int = _parse_int_env("BACKGROUND_EXECUTOR_WORKERS", 2)

    # =============================================================================
    # 日志配置 - 从 logger.py 迁移
    # =============================================================================
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_FORMAT: str = os.getenv(
        "LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # =============================================================================
    # HTTP 客户端配置 - 用于 LLM 调用
    # =============================================================================
    LLM_TIMEOUT_SECONDS: int = _parse_int_env("LLM_TIMEOUT_SECONDS", 120)
    LLM_HTTP_KEEPALIVE_CONNECTIONS: int = _parse_int_env(
        "LLM_HTTP_KEEPALIVE_CONNECTIONS", 20
    )
    LLM_HTTP_MAX_CONNECTIONS: int = _parse_int_env("LLM_HTTP_MAX_CONNECTIONS", 100)
    LLM_MAX_RETRIES: int = _parse_int_env("LLM_MAX_RETRIES", 2)

    # =============================================================================
    # 验证方法
    # =============================================================================
    @property
    def requires_api_key(self) -> bool:
        """Check if the current OPENAI_API_BASE requires an API key.

        Local endpoints (localhost/127.0.0.1) typically don't require keys.
        """
        base = self.OPENAI_API_BASE.lower()
        return not ("localhost" in base or "127.0.0.1" in base)

    def validate(self) -> None:
        """Validate the configuration.

        Raises:
            ValueError: If any configuration value is invalid.
        """
        # Validate API key for remote endpoints
        if self.requires_api_key and not self.OPENAI_API_KEY:
            raise ValueError(
                f"OPENAI_API_KEY is required for remote endpoint: {self.OPENAI_API_BASE}"
            )

        # Validate SCORE_THRESHOLD range
        if not 0.0 <= self.SCORE_THRESHOLD <= 1.0:
            raise ValueError(
                f"SCORE_THRESHOLD must be between 0.0 and 1.0, got {self.SCORE_THRESHOLD}"
            )

        # Validate port ranges
        for port_name, port_value in [
            ("QDRANT_PORT", self.QDRANT_PORT),
            ("API_PORT", self.API_PORT),
        ]:
            if not 1 <= port_value <= 65535:
                raise ValueError(
                    f"{port_name} must be between 1 and 65535, got {port_value}"
                )

        # Validate positive integers
        for name, value in [
            ("RAG_TOP_K", self.RAG_TOP_K),
            ("AGENT_MAX_ITERATIONS", self.AGENT_MAX_ITERATIONS),
            ("JOB_LEASE_TTL_SECONDS", self.JOB_LEASE_TTL_SECONDS),
            ("BACKGROUND_EXECUTOR_WORKERS", self.BACKGROUND_EXECUTOR_WORKERS),
        ]:
            if value <= 0:
                raise ValueError(f"{name} must be positive, got {value}")


# Create global config instance
config = Config()

# Validate on import (optional, can be disabled for tests)
# config.validate()
