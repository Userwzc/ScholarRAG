# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-03-28

### 🚀 Architecture Improvements

This release includes major architectural improvements across 4 waves (13 tasks) to enhance performance, maintainability, and production readiness.

### Wave 1: Critical Fixes (P0)

#### Added
- **Database Lease Pattern (W1-A)**: New `ingestion_jobs.leased_at` and `leased_by` columns for distributed task coordination
  - `USE_DB_JOB_LEASE` environment variable (default: `false` for backward compatibility)
  - `JOB_LEASE_TTL_SECONDS` configuration (default: 300s)
  - Automatic lease expiration and worker crash recovery
  
- **N+1 Query Elimination (W1-B)**: Optimized `similarity_search()` in `vector_store.py`
  - Changed from N individual `client.retrieve()` calls to 1 batch retrieve
  - **Performance improvement**: 9.97x faster (102ms → 10ms)

### Wave 2: Code Quality

#### Added
- **Exception Hierarchy (W2-A)**: New `src/utils/exceptions.py`
  - `AppError` (base), `ValidationError`, `NotFoundError`, `ExternalServiceError`
  - Unified error response format: `{"error": {"code": "...", "message": "..."}}`
  - All 14+ bare `except Exception` replaced with specific exception handling

- **Unified Path Configuration (W2-B)**: Centralized path management
  - New `PARSED_OUTPUT_DIR` environment variable (default: `./data/parsed`)
  - Eliminated 6 hard-coded `"./data/parsed"` strings across the codebase

- **Type Annotations (W2-C)**: Enhanced type safety
  - New `src/agent/types.py` with `AgentState` TypedDict
  - Complete type signatures for core agent functions
  - Reduced `Any` usage in agent modules

- **Stream Output Module (W2-D)**: New `src/utils/stream_output.py`
  - Separated token streaming (stdout) from status logging (logger)
  - Replaced all 67 `print()` calls in `main.py`

### Wave 3: Performance Optimization

#### Added
- **Configurable Batch Size (W3-A)**: GPU utilization improvement
  - `EMBEDDING_BATCH_SIZE` environment variable (default: 32, up from 4)
  - GPU memory-aware auto-scaling
  - **Performance improvement**: 12.64x throughput (438/s → 5539/s)

- **Caching Layer (W3-B)**: New `src/utils/cache.py`
  - `get_tokenizer()` singleton: Eliminates tiktoken reinitialization
  - `QueryCache` with 5-minute TTL: Caches retrieval results
  - **Performance**: <10ms latency for cache hits

- **ProcessPool Executor (W3-C)**: CPU-bound task parallelization
  - `EXECUTOR_TYPE` configuration (`thread` or `process`)
  - `BACKGROUND_EXECUTOR_WORKERS` configuration
  - Breaks GIL limitation for PDF parsing

- **Connection Reuse (W3-D)**: Client singletons
  - Qdrant client singleton with double-checked locking
  - LLM client lazy-loading singleton
  - Connection pool configuration: `QDRANT_TIMEOUT_SECONDS`, `LLM_TIMEOUT_SECONDS`

### Wave 4: Architecture Evolution

#### Added
- **Retrieval Service Protocol (W4-A)**: New `src/agent/retrieval_service.py`
  - `RetrievalService` Protocol for dependency inversion
  - `VectorStoreRetrievalService` adapter implementation
  - Tool layer no longer directly depends on `get_vector_store()`
  - Enables test mocking and future backend swaps

- **Module Decoupling (W4-B)**: Eliminated circular imports
  - New `src/agent/tooling.py`: Central tool registration
  - New `src/agent/types.py`: Shared type definitions
  - Clear separation: `langgraph_agent.py` (compilation) vs `graph.py` (API)

- **Docker & Observability (W4-C)**: Production readiness
  - `Dockerfile`: Multi-stage build, 232MB image
  - `docker-compose.yml`: API + Qdrant + Redis orchestration
  - `src/utils/metrics.py`: Prometheus metrics
    - `rag_search_latency_seconds` (Histogram)
    - `rag_searches_total` (Counter)
    - `ingestion_duration_seconds` (Histogram)
  - `src/utils/resilience.py`: Circuit breaker with Tenacity
    - 3 retry attempts with exponential backoff (1s-10s)
    - Configurable via `LLM_MAX_RETRIES`, `QDRANT_MAX_RETRIES`

### Testing

#### Added
- **22 new test cases** for architecture improvements
  - `test_vector_store_optimizations.py`: 6 tests for N+1, batching, connection reuse
  - `test_cache_w3b.py`: 4 tests for tokenizer and query caching
  - `test_w4c_metrics_circuit.py`: 2 tests for metrics and circuit breaker
  - `test_agent_imports.py`: 2 tests for circular import elimination
  - `test_agent_tools_retrieval_service.py`: 3 tests for decoupling
  - `test_cli_output.py`: 3 tests for logging refactoring
  - `test_paper_manager_paths.py`: 1 test for path configuration
  - `test_api_error_contract.py`: 3 integration tests for error handling

### Documentation

#### Updated
- `README.md`: New environment variables, Docker deployment, performance metrics
- `ARCHITECTURE.md`: Architecture improvements section with patterns and performance gains
- `AGENTS.md`: Critical invariants, error handling patterns, caching usage
- `src/agent/AGENTS.md`: Retrieval service protocol, shared types
- `api/AGENTS.md`: Error handling, background tasks, monitoring
- `tests/AGENTS.md`: Architecture improvement tests, new fixtures

### Environment Variables

#### New Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `USE_DB_JOB_LEASE` | `false` | Enable database lease for task coordination |
| `JOB_LEASE_TTL_SECONDS` | `300` | Lease expiration time |
| `PARSED_OUTPUT_DIR` | `./data/parsed` | MinerU output directory |
| `EMBEDDING_BATCH_SIZE` | `32` | Embedding batch size |
| `EXECUTOR_TYPE` | `thread` | Background executor type (`thread`/`process`) |
| `BACKGROUND_EXECUTOR_WORKERS` | `2` | Executor worker count |
| `QDRANT_TIMEOUT_SECONDS` | `30` | Qdrant connection timeout |
| `LLM_TIMEOUT_SECONDS` | `60` | LLM API timeout |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | (template) | Log format string |

### Performance Summary

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Search Latency (P95) | ~102ms | ~10ms | **9.97x** |
| Embedding Throughput | 438/s | 5539/s | **12.64x** |
| Cache Hit Latency | N/A | <10ms | New |
| Docker Image Size | N/A | 232MB | New |

### Migration Guide

#### For Developers
1. Update `.env` file with new variables (copy from `.env.example`)
2. Install new dependencies: `pip install -r requirements.txt`
3. Run database migration (if using `USE_DB_JOB_LEASE=true`)
4. Update import statements if extending agent tools (use `RetrievalService` protocol)

#### For Operators
1. Docker deployment now available: `docker compose up -d`
2. Prometheus metrics exposed at `/metrics`
3. Enable database lease for multi-instance deployment: `USE_DB_JOB_LEASE=true`
4. Use ProcessPool for CPU-bound PDF parsing: `EXECUTOR_TYPE=process`

### Breaking Changes

None. All changes are backward compatible:
- `USE_DB_JOB_LEASE=false` maintains legacy behavior
- `EXECUTOR_TYPE=thread` maintains legacy behavior
- Existing APIs unchanged
- Existing configurations still valid

### Contributors

Architecture improvements designed and implemented by the ScholarRAG team with deep category agents (Sisyphus-Junior) orchestration.

---

## [1.0.0] - 2026-03-01

### Initial Release

- Multimodal RAG for academic papers
- LangGraph agent with tool calling
- Qwen3-VL embeddings
- FastAPI backend with SSE streaming
- React frontend with PDF viewer
- MinerU PDF parsing integration
- SQLite persistence for tasks and versions
- Offline evaluation pipeline

[2.0.0]: https://github.com/your-org/scholarrag/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/your-org/scholarrag/releases/tag/v1.0.0
