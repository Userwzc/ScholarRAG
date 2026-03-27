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
