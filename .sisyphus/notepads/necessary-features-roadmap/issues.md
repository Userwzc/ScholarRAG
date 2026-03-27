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
