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
