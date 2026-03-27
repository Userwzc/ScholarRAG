# Issues - Task 1: Backend Test Harness

## Issue 1: Async Generator Not Subscriptable

**Error:** `TypeError: 'async_generator' object is not subscriptable`

**Cause:** pytest-asyncio was not properly configured to handle async fixtures.

**Fix:** Added `asyncio_mode = auto` to `pytest.ini`:
```ini
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
```

**Status:** RESOLVED

## Issue 2: Missing Optional Dependencies

**Error:** `ModuleNotFoundError: No module named 'sqlalchemy'`, `ModuleNotFoundError: No module named 'qdrant_client'`

**Cause:** Tests were importing modules that aren't installed in the test environment.

**Fix:** Added try/except blocks with `pytest.skip()`:
```python
try:
    from sqlalchemy.ext.asyncio import AsyncSession
except ImportError:
    pytest.skip("sqlalchemy not installed")
```

**Status:** RESOLVED

## Issue 3: qdrant_client Import in MockVectorStore

**Error:** `ModuleNotFoundError: No module named 'qdrant_client'` when calling `delete_paper()`

**Cause:** `delete_paper()` method was importing `qdrant_client.http.models` to create filter objects.

**Fix:** Replaced with simple dict-based filtering:
```python
def delete_paper(self, pdf_name: str) -> bool:
    to_delete = []
    for pid, item in self._store.items():
        meta = item["payload"].get("metadata", {})
        if meta.get("pdf_name") == pdf_name:
            to_delete.append(pid)
    for pid in to_delete:
        del self._store[pid]
    return True
```

**Status:** RESOLVED

## Issue 4: SQLAlchemy Missing During New Test Collection

**Error:** `ModuleNotFoundError: No module named 'sqlalchemy'` when collecting new schema/service tests.

**Cause:** Environment lacked SQLAlchemy runtime dependency while new tests imported SQLAlchemy at module import time.

**Fix:**
- Added `pytest.importorskip("sqlalchemy")` guard in new unit test module.
- Installed `sqlalchemy` and `aiosqlite` in environment for full execution.

**Status:** RESOLVED

## Issue 5: Pyright LSP Import Resolution Still Fails

**Error:** `reportMissingImports` for SQLAlchemy modules in LSP diagnostics despite runtime installation.

**Cause:** Pyright environment path is not aligned with runtime interpreter environment.

**Fix:** Runtime verification done with pytest; LSP warnings documented for environment alignment follow-up.

**Status:** OPEN

## Issue 6: Pyright import diagnostics for qdrant_client in service module

**Error:** `reportMissingImports` for `qdrant_client.http` in `paper_service.py`.

**Cause:** LSP environment does not expose optional qdrant dependency path consistently for module-level imports.

**Fix:** Moved qdrant import into `_build_filter()` and applied targeted type-ignore for missing-import diagnostics.

**Status:** RESOLVED

## Issue 7: Test patch path failed for lazy vector-store import in async job runner

**Error:** `AttributeError: module 'src.rag' has no attribute 'vector_store'` in unit tests patching `src.rag.vector_store.get_vector_store`.

**Cause:** `run_ingestion_job()` imported `get_vector_store` lazily inside function scope; patch target path was not resolvable in the test environment.

**Fix:** Added module helper `_get_vector_store()` in `async_upload_service` and patched that helper in tests.

**Status:** RESOLVED

## Issue 8: qdrant_client missing in lightweight unit-test environment for paper filters

**Error:** `ModuleNotFoundError: No module named 'qdrant_client'` when `paper_service._build_filter()` executed.

**Cause:** Filter builder imported qdrant models at runtime, but unit tests intentionally run without qdrant dependency.

**Fix:** Added a lightweight fallback filter/condition model in `paper_service._build_filter()` to preserve filter semantics in tests.

**Status:** RESOLVED

## Issue 9: Scope fidelity gap candidates found in final audit

**Observation:** Final F4 audit indicates potential partials:
- CI evaluation step runs `pytest tests/evaluation -v`, but does not explicitly run the offline runner command to emit/consume a JSON report as a gate artifact.
- Version history is API-accessible, but no obvious frontend version-history/reindex surface is present.

**Status:** OPEN

- 2026-03-27 Plan compliance audit: `ruff check .` currently fails on roadmap test files, so the CI backend lint gate cannot pass as-is.
- 2026-03-27 Plan compliance audit: `.github/workflows/ci.yml` runs `pytest tests/evaluation -v` instead of `python -m tests.evaluation.runner ...`, so CI does not gate on evaluation thresholds or guaranteed JSON report generation.
- 2026-03-27 Plan compliance audit: `src/agent/evidence_builder.py` imports `vector_store` directly and calls `fetch_by_metadata` with a plain dict, violating the Qdrant `models.Filter` guardrail and bypassing the lazy singleton path.
- 2026-03-27 Plan compliance audit: mandatory QA evidence files are present for tasks 1-6 and 8, but missing for tasks 7, 9, and 10 under `.sisyphus/evidence/`.
