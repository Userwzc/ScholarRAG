# Decisions - Task 1: Backend Test Harness

## Decision 1: Session-scoped Environment Fixture

**Context:** Tests need to run without GPU, Qdrant, or external APIs.

**Options:**
1. Per-test environment setup
2. Module-scoped fixture
3. Session-scoped autouse fixture

**Decision:** Session-scoped autouse fixture (`test_env`)

**Rationale:**
- Ensures environment is set before any module imports
- Avoids repeated setup/teardown overhead
- Guarantees isolation from real environment values
- Works with `env -u VAR` command to unset variables

## Decision 2: Mock Vector Store vs Real Qdrant

**Context:** Tests need to verify vector store interactions without real Qdrant.

**Options:**
1. Use real Qdrant in Docker for tests
2. Use in-memory Qdrant
3. Create mock implementation

**Decision:** Create `MockVectorStore` class

**Rationale:**
- No external dependencies for unit tests
- Deterministic behavior
- Fast execution
- Can be used in CI without Docker
- Real Qdrant tests can be marked as `@pytest.mark.integration`

## Decision 3: pytest-asyncio Mode

**Context:** Async fixtures and tests need proper handling.

**Options:**
1. `asyncio_mode = strict` (require explicit decorators)
2. `asyncio_mode = auto` (automatic detection)

**Decision:** `asyncio_mode = auto`

**Rationale:**
- Less boilerplate in test files
- Automatic detection of async fixtures and tests
- Works well with async generators for fixtures

## Decision 4: Dependency Handling

**Context:** Some tests require optional dependencies (sqlalchemy, qdrant_client).

**Options:**
1. Require all dependencies for tests
2. Skip tests when dependencies missing
3. Mock all dependencies

**Decision:** Skip tests when dependencies missing

**Rationale:**
- Allows running tests in minimal environments
- Tests still verify functionality when dependencies available
- Clear indication of what's being skipped
- CI can install full dependencies for complete coverage

## Decision 5: Test File Organization

**Context:** Need to organize tests for the roadmap features.

**Options:**
1. Flat structure in tests/
2. Separate unit/integration/evaluation directories
3. Mirror source structure

**Decision:** Separate unit/integration/evaluation directories

**Rationale:**
- Clear separation of test types
- Easy to run subsets with `-k "not integration"`
- Matches the plan's test categorization
- Allows different CI configurations per type

## Decision 6: Lightweight Internal Migration Registry

**Context:** Existing startup only called `Base.metadata.create_all()`, which does not provide explicit migration history.

**Options:**
1. Bring in Alembic now
2. Keep `create_all` only
3. Add minimal internal migration registry with versioned SQL

**Decision:** Add `schema_migrations` + versioned SQL bootstrap in `api/database.py`.

**Rationale:**
- Meets roadmap requirement for explicit, repeatable schema evolution
- Keeps implementation small and low-risk for current scope
- Remains idempotent across repeated startup runs

## Decision 7: Separate Registry/Job Service Modules

**Context:** New persistence behavior for papers/versions/jobs should not overload existing `paper_service.py` sync upload logic.

**Options:**
1. Add all logic into existing `paper_service.py`
2. Create focused persistence service modules

**Decision:** Create `paper_registry_service.py` and `ingestion_job_service.py`.

**Rationale:**
- Keeps route/service layering clean for follow-up tasks
- Isolates state-transition logic for targeted unit tests
- Avoids breaking current paper API behavior

## Decision 8: In-Process Duplicate Job Execution Guard

**Context:** Multiple background workers/threads could attempt to execute the same ingestion job concurrently.

**Options:**
1. Status check only (`job.status == processing`)
2. DB-level compare-and-set lock
3. In-process guard set + status checks

**Decision:** Use in-process guard (`_RUNNING_JOB_IDS`) plus DB status check before processing.

**Rationale:**
- Prevents duplicate execution races in current single-process background thread model
- Low-risk and minimal schema impact
- Works alongside durable `status/stage/progress` transitions

## Decision 9: Default Retrieval Is Current-Version Only

**Context:** Version history must be preserved, but default user flows must never leak stale chunks.

**Options:**
1. Filter only in API service layer
2. Filter in vector store methods by default + allow opt-out for explicit history reads
3. Filter in agent tools only

**Decision:** Apply `is_current=true` default filtering in vector store retrieval APIs, with `current_only=False` opt-out.

**Rationale:**
- Covers all retrieval callers (agent tools + paper APIs) consistently
- Reduces risk of missed filters in future endpoints
- Still supports explicit historical queries via `paper_version` filters

## Decision 10: Reindex Executes In Background Thread Entry Point

**Context:** Reindex endpoint must create a job and start processing asynchronously.

**Options:**
1. Run job synchronously in request thread
2. Reuse background ingestion launcher with daemon thread

**Decision:** Use daemon-thread `start_background_ingestion(job_id)` for async upload/retry/reindex routes.

**Rationale:**
- Keeps API contract non-blocking (`202 Accepted`)
- Reuses existing job worker logic
- Minimal change footprint without introducing external queue infra
