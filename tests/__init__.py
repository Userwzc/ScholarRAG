"""
ScholarRAG Test Suite.

This package contains all tests for the ScholarRAG project.

## Test Categories

- `unit/`: Fast unit tests with no external dependencies
- `integration/`: Tests requiring external services (Qdrant, GPU, etc.)
- `evaluation/`: Offline evaluation and regression tests

## Running Tests

```bash
# Run all unit tests (recommended for CI)
pytest tests -q -k "not integration"

# Run all tests including integration
pytest tests -q

# Run specific test file
pytest tests/unit/test_conftest.py -v
```
"""
