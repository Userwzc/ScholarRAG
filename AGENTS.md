# AGENTS.md — ScholarRAG

**Multimodal RAG for Academic Papers**

PDFs → MinerU → Qwen3-VL embedding → Qdrant → LangGraph agent → LLM

**Language:** Python 3.12 (backend) | TypeScript (frontend)  
**Key frameworks:** LangChain/LangGraph, HuggingFace, Qdrant, FastAPI, React

---

## Structure

```
ScholarRAG/
├── main.py              # CLI: add/query/delete
├── api/                 # FastAPI backend
│   ├── main.py          # App factory
│   ├── routes/          # REST endpoints
│   ├── services/        # Business logic
│   ├── models.py        # SQLAlchemy models
│   ├── schemas.py       # Pydantic models
│   └── database.py      # DB connection
├── frontend/            # React + TypeScript SPA
│   └── src/
│       ├── pages/       # Route views
│       ├── components/  # UI components
│       ├── stores/      # Zustand state
│       └── lib/         # Utilities
├── config/              # Pydantic settings
├── tests/               # Test suites
│   ├── unit/            # Unit tests
│   ├── integration/     # Integration tests
│   └── evaluation/      # Offline evaluation
└── src/
    ├── core/            # Shared business logic
    ├── agent/           # LangGraph (see src/agent/AGENTS.md)
    ├── custom/          # Qwen3-VL models (see src/custom/AGENTS.md)
    ├── ingest/          # MinerU PDF parsing
    ├── rag/             # Qdrant vector store
    ├── utils/           # Logger, cache, exceptions
    └── jobs/            # Async task management
```

**Module stats:**
- `src/agent/`: 9 files, 2,032 lines
- `api/`: 17 files, 2,669 lines  
- `frontend/src/`: 20 files, 3,012 lines
- `tests/`: 31 files, 7,491 lines

**Module-specific docs:**
- `src/agent/AGENTS.md` — LangGraph agent patterns
- `src/custom/AGENTS.md` — Qwen3-VL model wrappers
- `api/AGENTS.md` — FastAPI backend patterns
- `frontend/src/AGENTS.md` — React frontend patterns

---

## Tech Stack

| Layer | Technology | Key Frameworks |
|-------|------------|----------------|
| **Backend** | Python 3.12 | FastAPI, LangChain/LangGraph, PyTorch, Qdrant |
| **Frontend** | TypeScript, React 19 | Vite, Tailwind CSS 4, Zustand, React Router |
| **PDF Parsing** | MinerU | Academic document parsing |
| **Embedding** | Qwen3-VL | Multimodal embeddings |

---

## Entry Points

| Type | File | Purpose | Command |
|------|------|---------|---------|
| **CLI** | `main.py` | Command-line interface | `python main.py {add,query,delete}` |
| **API** | `api/main.py` | FastAPI application | `uvicorn api.main:app --host 0.0.0.0 --port 8000` |
| **Frontend** | `frontend/src/main.tsx` | React app entry | `cd frontend && npm run dev` |
| **Evaluation** | `tests/evaluation/runner.py` | Offline evaluation | `python -m tests.evaluation.runner` |

---

## Quick Start

```bash
# Backend
conda activate scholarrag
python main.py add paper.pdf
python main.py query "What is the methodology?"
uvicorn api.main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend && npm run dev  # http://localhost:5173
```

---

## Critical Invariants

| Rule | Constraint |
|------|------------|
| **Vector Store** | Access via `get_vector_store()` — never import `vector_store` directly; singleton uses double-checked locking |
| **CUDA/vLLM** | Call `get_vector_store()` inside functions **after** MinerU parsing completes; never at module level |
| **Idempotent IDs** | Use `uuid.uuid5()` based on content; never `uuid.uuid4()` |
| **Filters** | Use `qdrant_client.http.models.Filter`; never custom DSL dicts |
| **System Prompts** | Use `SystemMessage`; never `HumanMessage` |
| **Tool Calls** | Agent must call at least one tool before answering |
| **Message Types** | Import from `langchain_core.messages`: `AIMessage`, `HumanMessage`, `ToolMessage` |
| **Error Handling** | Use specific exception types from `src/utils/exceptions`; never bare `except Exception` |
| **Retrieval Service** | Agent tools use `RetrievalService` protocol; never directly import `get_vector_store()` in tools |
| **N+1 Queries** | Batch retrieve operations; never loop with individual `client.retrieve()` calls |

---

## Code Style — Python

### Imports
```python
# Order: stdlib → third-party → local (blank lines between)
import os

from dotenv import load_dotenv

from config.settings import config  # cross-package
from .embedding import X          # within package
```
- Never import inside functions except heavy deps (MinerU, vector_store, agent_app)
- Use `# noqa: E402` for imports after `load_dotenv()`

### Types & Naming
- Annotate all function signatures
- Python 3.9+ generics: `list[str]`, `dict[str, Any]` (not `List[str]`)
- Optional params: `Optional[T]` (not `T \| None`)
- Classes: `PascalCase` | Functions: `snake_case` | Constants: `UPPER_SNAKE_CASE`

### Logging
```python
from src.utils.logger import get_logger
logger = get_logger(__name__)

logger.info("Action %s completed", item)  # lazy % formatting
# Never use print() except streaming in query_agent()
```

### Error Handling
```python
from src.utils.exceptions import AppError, ValidationError, NotFoundError

# Raise specific exceptions
def get_paper(pdf_name: str) -> Paper:
    if not pdf_name:
        raise ValidationError("pdf_name is required")
    # ...
    if paper is None:
        raise NotFoundError(f"Paper '{pdf_name}' not found")
```

### Caching
```python
from src.utils.cache import get_tokenizer, QueryCache

# Tokenizer singleton
tokenizer = get_tokenizer("cl100k_base")  # cached across calls

# Query cache for retrieval
query_cache = QueryCache(ttl=300)  # 5 minutes TTL
```

### PyTorch
```python
@torch.no_grad()
def inference(self, ...):
    tensor = tensor.to(self.model.device)
    # ...

torch.cuda.empty_cache()  # after batch processing
```
- Use `bfloat16` if supported, else `float16`
- Call `model.eval()` after loading

### Configuration
```python
# config/settings.py — never hardcode
RAG_TOP_K: int = _parse_int_env("RAG_TOP_K", 5)  # not int(os.getenv(...))
QDRANT_COLLECTION_NAME: str = _parse_str_env("QDRANT_COLLECTION_NAME", "scholarrag")
```

### Testing
- Unit tests: `@pytest.mark.unit` — no external deps
- Integration tests: `@pytest.mark.integration` — requires Qdrant, GPU
- Fixtures in `conftest.py`: `test_env`, `temp_db`, `mock_vector_store`
- Mock external deps; never call real APIs in unit tests

---

## Code Style — TypeScript/React

### Naming
- Components: `PascalCase.tsx` in `components/` or `pages/`
- Hooks: `useCamelCase.ts` in `hooks/`
- Stores: `kebab-store.ts` using Zustand in `stores/`
- Utils: `camelCase` in `lib/`

### Patterns
```typescript
function Foo(): React.JSX.Element {  // explicit return type
  const { data } = useQuery(...)  // @tanstack/react-query
  // ...
}
```

---

## Things to Avoid

| Pattern | Why | Correct Alternative |
|---------|-----|---------------------|
| Commit `.env`, `models/`, `data/`, `qdrant_storage/` | Security/Size | Add to `.gitignore` |
| Use `print()` for logging | Uncontrolled output | Use `get_logger(__name__)` (except streaming in `query_agent()`) |
| Hard-code paths, URLs, credentials | Inflexible | Use `config.settings` |
| `client.search()` | Deprecated API | Use `client.query_points(...).points` |
| Hard-code `top_k=5` | Not configurable | Read `config.RAG_TOP_K` |
| `stream_mode="values"` | Breaks streaming logic | Keep default `"messages"` |
| `List[...]`, `Dict[...]` from `typing` | Old syntax | Use `list[...]`, `dict[...]` |
| Bare `except Exception` | Catches too much | Catch specific `AppError` types |
| Import `get_vector_store()` at module level in tools | Tight coupling | Use `RetrievalService` protocol |
| `uuid.uuid4()` for content IDs | Non-idempotent | Use `uuid.uuid5()` for idempotency |
| `HumanMessage` for system prompts | Wrong message type | Use `SystemMessage` |
| Loop with individual `client.retrieve()` calls | N+1 query problem | Batch retrieve operations |
| Custom DSL dicts for Qdrant filters | Incompatible | Use `qdrant_client.http.models.Filter` |
| Direct `vector_store` import | Returns None | Use `get_vector_store()` function |
| Module-level `get_vector_store()` import | CUDA/vLLM conflict | Call inside functions after MinerU parsing |

---

## Project-Specific Patterns (Non-standard)

| Pattern | Standard | This Project | Rationale |
|---------|----------|--------------|-----------|
| **Dependency Management** | `pyproject.toml` (PEP 621) | `requirements.txt` | Simple, direct, easy for users |
| **Vector Store Access** | Direct `from rag import vector_store` | Must call `get_vector_store()` singleton | Thread-safe + lazy init, avoids CUDA conflicts |
| **ID Generation** | `uuid.uuid4()` random | `uuid.uuid5()` content-based | Idempotent writes |
| **Agent Pattern** | Simple function calls | LangGraph state machine | Complex multi-step reasoning |
| **Exception Handling** | `raise Exception` | Custom `AppError` hierarchy | Unified error handling |
| **Logging** | `print()` or generic logger | `get_logger(__name__)` | Normalized log output |
| **Import Restriction** | Free imports | Tools can't directly import `get_vector_store()` | Decoupled via `RetrievalService` protocol |
| **Configuration** | `dataclasses` | Pydantic Settings | Type-safe + env binding |
| **Documentation** | Single README | Module-level `AGENTS.md` files | Record module-specific conventions |

---

## Vector Store API

```python
from src.rag.vector_store import get_vector_store

store = get_vector_store()  # singleton, lazy initialization, thread-safe

# Methods
store.add_multimodal(inputs, metadatas)
store.similarity_search(query, k, filter)
store.delete_paper(pdf_name)

# Filter construction
from qdrant_client.http import models
filter = models.Filter(
    must=[models.FieldCondition(
        key="metadata.pdf_name",
        match=models.MatchValue(value="paper")
    )]
)
```

- `similarity_search` is the only supported search method; alias methods are removed.
- 当前检索为 hybrid-only；仅返回检索结果。
- `get_vector_store()` is safe for concurrent access via double-checked locking.

---

## CI/CD Pipeline

GitHub Actions workflow (`.github/workflows/ci.yml`):

| Job | Steps |
|-----|-------|
| **backend** | `ruff check` → `ruff format --check` → `bandit` → `pytest` (cov≥35%) |
| **evaluation** | `python -m tests.evaluation.runner` (non-blocking) |
| **frontend** | `npm ci` → `npm run lint` → `npm run build` |

**Non-standard patterns:**
- Evaluation runs with `continue-on-error: true` (doesn't block builds)
- Coverage threshold: 35% (relatively low)
- Frontend has no automated tests (lint + build only)
- Redis service defined in docker-compose but unused in code

---

## Docker

```bash
docker build -t scholarrag .
docker compose up -d
```

**Services:** api (FastAPI), qdrant (vector DB)

---

## Test Infrastructure

```bash
# Unit tests only (CI default)
pytest tests -q -k "not integration"

# All tests (requires Qdrant + GPU)
pytest tests -q

# Evaluation pipeline
python -m tests.evaluation.runner \
  --dataset tests/evaluation/dataset.json \
  --output reports/evaluation_report.json \
  --thresholds-file tests/evaluation/thresholds.json
```

**Test categories:**
- `@pytest.mark.unit` — No external deps, fast
- `@pytest.mark.integration` — Requires Qdrant, GPU
- `@pytest.mark.slow` — Long-running tests

**Key fixtures:** `test_env`, `temp_db`, `mock_vector_store`, `sample_paper_payload`

---

## Lint / Test

```bash
# Python
ruff check .        # lint
ruff check --fix .  # auto-fix
ruff format .       # format
pytest              # run tests

# Frontend
cd frontend && npm run lint
```
