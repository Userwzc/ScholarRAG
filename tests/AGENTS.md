# AGENTS.md — Tests

Testing infrastructure: pytest fixtures, evaluation pipeline, CI/CD integration.

## Structure

```
tests/
├── conftest.py                         # Shared fixtures (755 lines)
├── unit/                               # Unit tests (no external deps)
│   ├── test_vector_store_optimizations.py  # W1-B, W3-A, W3-D: 检索性能优化
│   ├── test_cache_w3b.py               # W3-B: Tokenizer/查询缓存
│   ├── test_w4c_metrics_circuit.py     # W4-C: 监控指标与断路器
│   ├── test_agent_imports.py           # W4-B: 循环导入消除验证
│   ├── test_agent_tools_retrieval_service.py  # W4-A: 工具层解耦
│   ├── test_cli_output.py              # W2-D: CLI 输出规范
│   ├── test_paper_manager_paths.py     # W2-B: 路径配置统一
│   └── ...
├── integration/                        # Integration tests (requires Qdrant/GPU)
│   └── test_api_error_contract.py      # W2-A: API 错误响应规范
├── evaluation/                         # Offline evaluation pipeline
│   ├── runner.py                       # Evaluation orchestrator
│   ├── metrics.py                      # Retrieval metrics
│   ├── dataset.py                      # Dataset loader
│   └── thresholds.json                 # Pass/fail criteria
└── fixtures/                           # Test data
    └── pdfs/                           # Sample PDFs
```

## Test Categories

| Category | Mark | External Deps | When to Run |
|----------|------|---------------|-------------|
| Unit | `@pytest.mark.unit` | None | Always (CI default) |
| Integration | `@pytest.mark.integration` | Qdrant, GPU | Local/CI with services |
| Slow | `@pytest.mark.slow` | Varies | Optional |

## Running Tests

```bash
# Unit tests only (default for CI)
pytest tests -q -k "not integration"

# All tests (requires Qdrant + GPU)
pytest tests -q

# Specific category
pytest tests/unit -v
pytest tests/evaluation -v

# With explicit env isolation
env -u OPENAI_API_KEY -u EMBEDDING_MODEL pytest tests -q
```

## Fixtures (conftest.py)

| Fixture | Purpose |
|---------|---------|
| `test_env` | Auto-mocked env vars (session-scoped) |
| `temp_db` | Isolated SQLite database |
| `mock_vector_store` | Fake vector store (no GPU) |
| `sample_paper_payload` | Representative parsed paper data |
| `sample_pdf_path` | Minimal test PDF path |

## Architecture Improvement Tests

### Performance Optimization Tests
- **test_vector_store_optimizations.py**: 验证 N+1 查询消除、batch_size 配置、连接复用
  - `test_similarity_search_no_n_plus_1`: 确保检索只执行 1 次 search + 1 次 batch retrieve
  - `test_embedding_batch_size_config_default_and_override`: 验证批大小可配置
  - `test_qdrant_client_singleton_reuse`: 验证 client 单例复用

### Caching Tests
- **test_cache_w3b.py**: 验证 Tokenizer 和查询缓存
  - `test_tokenizer_initialized_once_across_calls`: Tokenizer 单例
  - `test_query_cache_hit_avoids_second_vector_search`: 缓存命中避免重复检索
  - `test_query_cache_hit_latency_under_10ms`: 缓存命中延迟 <10ms

### Architecture Decoupling Tests
- **test_agent_imports.py**: 验证循环导入消除
- **test_agent_tools_retrieval_service.py**: 验证工具层通过协议解耦向量存储

### Error Handling Tests
- **test_api_error_contract.py**: 验证 API 错误响应格式统一

## Evaluation Pipeline

**Offline evaluation** for RAG quality metrics:

```bash
# Run evaluation
python -m tests.evaluation.runner \
  --dataset tests/evaluation/dataset.json \
  --output reports/evaluation_report.json \
  --thresholds-file tests/evaluation/thresholds.json
```

**Metrics tracked:**
- Retrieval Hit Rate
- Page Hit Rate  
- Keyword Match Rate
- Citation Coverage Rate
- Current Version Leak Rate
- Failed Query Rate

**CI behavior:** Evaluation runs with `continue-on-error: true` — failures don't block builds.

## Testing Conventions

1. **Mock external deps**: Unit tests use mocks; never call real APIs
2. **Fixture reuse**: Shared fixtures in conftest.py, not per-file setup
3. **Env isolation**: Tests set `EMBEDDING_MODEL=mock-model`, `OPENAI_API_KEY=test-key-mock`
4. **Temp paths**: Use `/tmp/scholarrag_test_*` for test artifacts
5. **Deterministic**: Fixtures provide fixed seeds/UUIDs where possible

## CI Integration

GitHub Actions runs:
1. `ruff check .` — Backend lint
2. `ruff format --check .` — Backend format check  
3. `bandit -r src/ -ll` — Security scan
4. `pytest tests -k "not integration" --cov=src --cov-fail-under=35` (unit tests with coverage)
5. `npm run lint` — Frontend lint (no tests currently)
6. `npm run build` — Frontend build
7. `python -m tests.evaluation.runner` (non-blocking, `continue-on-error: true`)

See `.github/workflows/ci.yml` for full pipeline.
