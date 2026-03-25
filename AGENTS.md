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
│   └── services/        # Business logic
├── frontend/            # React + TypeScript SPA
│   └── src/
│       ├── pages/       # Route views
│       ├── components/  # UI components
│       └── stores/      # Zustand state
├── config/              # Pydantic settings
└── src/
    ├── core/            # Shared business logic
    ├── agent/           # LangGraph (see src/agent/AGENTS.md)
    ├── custom/          # Qwen3-VL models (see src/custom/AGENTS.md)
    ├── ingest/          # MinerU PDF parsing
    └── rag/             # Qdrant vector store
```

**Module-specific docs:**
- `src/agent/AGENTS.md` — LangGraph agent patterns
- `src/custom/AGENTS.md` — Qwen3-VL model wrappers
- `api/AGENTS.md` — FastAPI backend patterns
- `frontend/src/AGENTS.md` — React frontend patterns

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

---

## Code Style — TypeScript/React

### Naming
- Components: `PascalCase.tsx` in `components/` or `pages/`
- Hooks: `useCamelCase.ts` in `hooks/`
- Stores: `kebab-store.ts` using Zustand in `stores/`
- Utils: `camelCase` in `lib/`

### Patterns
```typescript
function Foo(): JSX.Element {  // explicit return type
  const { data } = useQuery(...)  // @tanstack/react-query
  // ...
}
```

---

## Things to Avoid

- Don't commit `.env`, `models/`, `data/`, `qdrant_storage/`
- Don't use `print()` for logging (except streaming)
- Don't hard-code paths, URLs, or credentials
- Don't use deprecated `client.search()` — use `client.query_points(...).points`
- Don't hard-code `top_k=5` — read `config.RAG_TOP_K`
- Don't switch `stream_mode` to `"values"` in `query_agent()`
- Don't use `List`, `Dict` from `typing` — use `list`, `dict`

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
