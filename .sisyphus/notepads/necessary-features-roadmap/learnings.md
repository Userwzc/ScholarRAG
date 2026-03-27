# Learnings - Task 1: Backend Test Harness

## pytest-asyncio Configuration

**Issue:** Async fixtures were not being properly resolved, causing `TypeError: 'async_generator' object is not subscriptable`.

**Solution:** Add `asyncio_mode = auto` to `pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
```

This allows pytest-asyncio to automatically handle async fixtures and test functions without requiring explicit `@pytest.mark.asyncio` decorators on every async test.

## Environment Isolation Pattern

**Pattern:** Use session-scoped autouse fixture for environment isolation:
```python
@pytest.fixture(scope="session", autouse=True)
def test_env() -> Generator[dict[str, str], None, None]:
    # Store original values
    original_env: dict[str, str | None] = {}
    test_env_vars = {...}
    
    # Set test values
    for key, value in test_env_vars.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value
    
    yield test_env_vars
    
    # Restore original values
    for key, original_value in original_env.items():
        if original_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original_value
```

**Why session scope:** Ensures env is set before any module imports happen.

## Mock Vector Store Design

**Key insight:** The mock vector store should not depend on `qdrant_client` for basic operations. Only import it when needed for filter matching.

**Implementation:** Simple in-memory dict with filter matching logic that mimics Qdrant's Filter/FieldCondition API.

## Graceful Dependency Handling

**Pattern:** Use `pytest.skip()` for tests that require optional dependencies:
```python
def test_something():
    try:
        from optional_module import Something
    except ImportError:
        pytest.skip("optional_module not installed")
```

This allows the test suite to run in minimal environments while still testing full functionality when dependencies are available.

## Test Organization

```
tests/
├── __init__.py
├── conftest.py           # Shared fixtures
├── fixtures/             # Test data
│   ├── __init__.py
│   ├── sample_papers.py
│   └── pdfs/
├── unit/                 # Fast unit tests
│   ├── __init__.py
│   └── test_conftest.py
├── integration/          # Tests requiring external services
└── evaluation/           # Offline evaluation tests
```

## Task 2 Learning: Migration Bootstrap Pattern

- Keep `Base.metadata.create_all()` for compatibility, but run explicit versioned SQL migrations afterward via `schema_migrations`.
- Use `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` for idempotent bootstrap.
- For SQLite schema evolution, guard `ALTER TABLE ... ADD COLUMN` with `PRAGMA table_info()` checks.

## Task 2 Learning: Version Toggle Semantics

- New version creation should atomically flip prior `is_current=True` rows to `False` before inserting the next current version.
- Version numbering is simplest and deterministic when derived from max existing `version_number` per paper.

## Task 2 Learning: Durable Job Transition Fields

- Store `status`, `stage`, `progress`, `retry_count`, `result_summary`, and `error_message` directly in `ingestion_jobs`.
- Normalize status values (`pending/processing/completed/failed`) in service layer to keep writes consistent.

## Task 3 Learning: Async Upload API Design

- Route ordering matters in FastAPI: `/uploads` routes must come before `/{pdf_name}` routes to avoid path conflicts.
- Use `selectinload()` for eager loading relationships in async SQLAlchemy to avoid `MissingGreenlet` errors.
- Staged files should be stored in job-scoped directories (`staged/{job_id}/filename.pdf`) for retry support.
- The `get_db_session()` context manager from `api.database` provides automatic commit/rollback for route handlers.
- HTTP 202 Accepted is the correct status code for async job creation endpoints.
- HTTP 409 Conflict is appropriate for retry rejection on non-failed jobs.

## Task 3 Learning: Non-Breaking API Extension

- Keep existing sync `/upload` endpoint unchanged for backward compatibility.
- New async endpoints use `/uploads` (plural) to distinguish from sync `/upload`.
- Job status includes all fields needed for frontend polling: status, stage, progress, retry_count, error_message, result.

## Task 4 Learning: Progress Callback Threading Pattern

- Keep `process_paper()` synchronous but accept `progress_callback(stage, progress)` so parse/chunk stages are observable without changing CLI callers.
- In async ingestion workers, run heavy sync ingestion via `asyncio.to_thread(...)` and bridge callback updates back to DB with `asyncio.run_coroutine_threadsafe(...)` for durable stage/progress writes.
- Use explicit monotonic stages: `queued -> parsing -> chunking -> storing -> finalizing -> completed/failed`.

## Task 5 Learning: Structured Provenance Design

- Provenance should be built from collected evidence after the agent loop completes, not during streaming.
- Deduplicate by `(pdf_name, page, type)` tuple to avoid duplicate citations for same chunk.
- `paper_version` field is optional and will be populated by Task 6 (version-aware reindex).
- Supporting text should be truncated (200 chars) to keep payloads reasonable.
- Empty evidence should return empty `sources` array, not fabricated citations.

## Task 5 Learning: Lazy Import for Vector Store

- The `vector_store` module imports heavy dependencies (`langchain_qdrant`, `torch`).
- Import `vector_store` inside functions that need it, not at module level.
- This allows tests to run without GPU/Qdrant dependencies when testing pure logic functions.
- Pattern: `from src.rag.vector_store import vector_store` inside try/except block.

## Task 5 Learning: SSE Event Extension

- SSE events are passed through as-is with `json.dumps(event)`.
- Adding new fields to existing event types (like `sources` to `answer_done`) is backward compatible.
- Frontend consumers can ignore unknown fields without breaking.
- Pydantic `SourceSchema` with optional fields allows gradual adoption.

## Task 6 Learning: Version Metadata Must Be Written At Ingestion Source

- Add `paper_version` and `is_current` directly in `process_paper()` metadata assembly so every chunk carries version identity regardless of caller (CLI/API/async job).
- Deterministic UUIDs must include `paper_version` in `vector_store._content_uuid(...)` inputs, otherwise reindex writes collide with previous-version points.

## Task 6 Learning: Current-Version Filtering Should Default in Vector Store APIs

- Enforcing `metadata.is_current == true` as a default in `similarity_search`, `scroll_chunks`, `fetch_by_metadata`, `count_chunks`, and `get_all_papers` prevents stale-version leakage across agent search and paper endpoints.
- Keep explicit historical access by allowing callers to pass `current_only=False` plus a `paper_version` metadata filter.

## Task 6 Learning: Reindex Lifecycle Requires DB+Vector Synchronization

- `run_ingestion_job()` should create and link a `PaperVersion` row before final job completion, and include the version number in job result summaries.
- After successful reindex writes, mark previous-version vector payloads `is_current=false` to align vector-store retrieval with version lifecycle state.

## Task 7 Learning: Frontend Async Upload Job UI

- Use `useSearchParams` from react-router-dom to read query parameters for deep-linking
- Avoid calling setState in useEffect - use a custom hook to compute initial state from URL params
- When spreading API response types into UI types, ensure all required fields are present
- `IngestionJobResponse` has `result.pdf_name` while `IngestionJobListItem` has `pdf_name` directly - need to map between them
- Use TanStack Query's `refetchInterval` for polling job status instead of manual intervals
- Job cards should show progress bar for processing state, retry button for failed state

## Task 7 Learning: Citation Deep-Link Pattern

- Use Link component from react-router-dom with query params: `to={\`/papers/\${pdf_name}/read?page=\${page}\`}`
- Page numbers in URLs are 1-indexed (user-facing), but PDF viewer uses 0-indexed internally
- Convert page param: `parseInt(pageParam, 10) - 1`
- Sources from backend `answer_done` event include structured provenance (chunk_id, paper_version, heading, supporting_text)

## Task 7 Learning: Conversation Store Source Type Extension

- Extend Source interface with optional provenance fields: chunk_id, paper_version, heading, supporting_text
- Update loadConversationMessages mapping to include new fields
- Backend MessageResponse.sources uses SourceSchema which already has these fields

## Task 7 Learning: Frontend Async Upload Job UI

- Use useSearchParams from react-router-dom to read query parameters for deep-linking
- Avoid calling setState in useEffect - use a custom hook to compute initial state from URL params
- When spreading API response types into UI types, ensure all required fields are present
- IngestionJobResponse has result.pdf_name while IngestionJobListItem has pdf_name directly - need to map between them
- Use TanStack Query refetchInterval for polling job status instead of manual intervals
- Job cards should show progress bar for processing state, retry button for failed state

## Task 7 Learning: Citation Deep-Link Pattern

- Use Link component from react-router-dom with query params for deep-linking
- Page numbers in URLs are 1-indexed (user-facing), but PDF viewer uses 0-indexed internally
- Convert page param: parseInt(pageParam, 10) - 1
- Sources from backend answer_done event include structured provenance (chunk_id, paper_version, heading, supporting_text)

## Task 7 Learning: Conversation Store Source Type Extension

- Extend Source interface with optional provenance fields: chunk_id, paper_version, heading, supporting_text
- Update loadConversationMessages mapping to include new fields
- Backend MessageResponse.sources uses SourceSchema which already has these fields

## Task 8 Learning: Offline Evaluation Runner Design

- Evaluation runner should be executable as a module: `python -m tests.evaluation.runner`
- Use dataclasses for all evaluation data structures (EvalQuery, EvalDataset, QueryResult, EvaluationMetrics, EvaluationReport)
- Metrics should be deterministic and cheap: retrieval_hit_rate, page_hit_rate, keyword_match_rate, citation_coverage_rate, current_version_leak_rate, failed_query_rate
- Exit codes: 0 for success, 1 for threshold failure, 2 for runtime errors
- Support CLI args for dataset path, output path, top_k, and threshold overrides

## Task 8 Learning: Version-Aware Metrics

- `current_version_leak_rate` detects when non-current versions leak into default retrieval results
- Check `is_current=False` in retrieved chunk metadata to detect leaks
- Zero tolerance (0.0) is the default threshold for version leaks

## Task 8 Learning: Provenance-Aware Metrics

- `citation_coverage_rate` checks if retrieved chunks have required provenance fields
- Required fields: pdf_name, page, type
- Optional fields: chunk_id, paper_version, heading
- Empty pdf_name should fail citation coverage check

## Task 8 Learning: Threshold Configuration

- Default thresholds are conservative: retrieval_hit_rate=0.5, page_hit_rate=0.3, keyword_match_rate=0.3
- Citation coverage threshold is high (0.8) to ensure quality
- Version leak threshold is zero (0.0) - no tolerance for stale data
- Failed query rate threshold is 0.1 to allow some failures

## Task 8 Learning: JSON Report Structure

- Report includes: timestamp, dataset_name, dataset_version, mode, top_k, metrics, thresholds, verdict
- All metrics are machine-readable for CI consumption
- Verdict includes pass/fail status and list of specific failures
- Query results are included for debugging

## Task 8 Learning: Dataset Fixture Pattern

- Default dataset is embedded in code for reproducibility
- External datasets can be loaded from JSON files
- Dataset includes: name, version, description, queries
- Each query has: question, expected_pdf, expected_pages, keywords, expected_chunk_ids, expected_version

## Scope Fidelity Check Learning (F4)

- Core roadmap features are present end-to-end, but strict scope-fidelity review should separately verify **contract completeness** (e.g., CI actually consuming evaluation JSON artifacts, not only evaluation unit tests).
- Version history is exposed via API (`GET /api/papers/{pdf_name}/versions`), while frontend currently emphasizes job/provenance UX; explicit version-history UI remains a potential gap depending on acceptance interpretation.
