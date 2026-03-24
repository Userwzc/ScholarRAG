# AGENTS.md — ScholarRAG Coding Guidelines

## Project Overview

Multimodal RAG system for academic papers: PDFs → MinerU → Qwen3-VL embedding → Qdrant → LangGraph agent → LLM.

**Language:** Python 3.12 (backend) | TypeScript (frontend)  
**Key frameworks:** LangChain / LangGraph, HuggingFace Transformers, Qdrant, MinerU, PyTorch, FastAPI, React

## Project Structure

```
ScholarRAG/
├── main.py                 # CLI: add/query/delete subcommands
├── api/                    # FastAPI backend
│   ├── main.py            # App factory, CORS, router mounting
│   ├── config.py          # API-specific config (host, port, upload dir)
│   ├── schemas.py         # Pydantic request/response models
│   ├── routes/            # Endpoint handlers
│   └── services/          # Business logic layer
├── frontend/              # React + TypeScript SPA
│   ├── src/
│   │   ├── components/    # Reusable UI (shadcn/ui pattern)
│   │   ├── pages/         # Route-level views
│   │   ├── hooks/         # Custom React hooks
│   │   ├── stores/        # Zustand state management
│   │   └── lib/           # Utility functions
│   └── package.json
├── config/settings.py     # Config dataclass; reads .env
├── src/
│   ├── core/              # Shared business logic (ingestion.py)
│   ├── agent/             # LangGraph: graph.py, tools.py, langgraph_agent.py
│   ├── custom/            # Qwen3-VL model wrappers: embedding, reranker, vision_utils
│   ├── ingest/            # MinerU parser, paper_manager
│   ├── rag/               # embedding.py, vector_store.py, reranker_strategy.py
│   └── utils/             # logger.py
└── data/parsed/           # MinerU output (gitignored)
```

## Environment

```bash
conda activate scholarrag
```

`.env` (never commit): `OPENAI_API_BASE`, `OPENAI_API_KEY`, `QDRANT_HOST`, `QDRANT_PORT`, `LLM_MODEL`, `EMBEDDING_MODEL`, `MINERU_MODEL_SOURCE`, `MINERU_BACKEND`, `RERANKER_MODEL`, `RAG_TOP_K`, `SCORE_THRESHOLD`, `AGENT_MAX_ITERATIONS`, `LOG_LEVEL`, `API_HOST`, `API_PORT`, `API_UPLOAD_DIR`, `ENABLE_HYBRID`

## Run Commands

```bash
# Backend (Python)
python main.py add <path/to/paper.pdf>   # Ingest PDF
python main.py query "<question>"        # Query RAG agent
python main.py delete <pdf_name>         # Remove paper
uvicorn api.main:app --host 0.0.0.0 --port 8000  # FastAPI server

# Frontend (Node.js)
cd frontend && npm run dev               # Development server (port 5173)
cd frontend && npm run build             # Production build
cd frontend && npm run lint              # ESLint
```

## Lint / Test

```bash
# Python
ruff check .           # lint
ruff check --fix .     # auto-fix
ruff format .          # format

pytest                           # run all tests
pytest tests/test_file.py        # run one file
pytest tests/test_file.py::test_func  # run one test function
pytest -x                        # stop on first failure

# Frontend
cd frontend && npm run lint      # ESLint
```

Place tests in `tests/test_<module>.py`.

## Code Style — Python

### Imports
- Order: stdlib → third-party → local (blank lines between)
- Cross-package: `from config.settings import config`
- Within package: `from .embedding import X`
- Never import inside functions except for optional heavy deps (MinerU, PaperManager, vector_store, agent_app)
- Use `# noqa: E402` for imports after `load_dotenv()` call

### Types & Naming
- Annotate all function signatures with parameter and return types
- Python 3.9+ generics: `list[str]`, `dict[str, Any]` (not `List[str]`, `Dict[str, Any]`)
- Use `Optional[T]` for optional parameters, not `T | None` in type hints
- Classes: `PascalCase` | Functions: `snake_case` | Constants: `UPPER_SNAKE_CASE` | Loggers: `logger`
- Private methods: `_leading_underscore`

### Error Handling
- Catch specific exceptions; avoid bare `except:`
- Log before re-raising: `logger.error("Failed: %s", exc)`
- `ValueError` for bad args, `TypeError` for wrong types, `FileNotFoundError` for missing paths
- Use `raise ... from None` to suppress chain when appropriate

### Logging
- Use `get_logger(__name__)` — never `print()` except for streaming in `query_agent()`
- Format: `logger.info("Action %s completed", item)` (lazy % formatting)
- Include context in log messages for debugging

### PyTorch
- `@torch.no_grad()` decorator on inference methods
- Move tensors to `self.model.device` explicitly
- Call `model.eval()` after loading
- Use `torch.bfloat16` if `torch.cuda.is_bf16_supported()`, else `torch.float16`
- Call `torch.cuda.empty_cache()` after batch processing in loops

### Configuration
- All tunable values in `config/settings.py` — never hardcode
- Integer env vars: `_parse_int_env(name, default)` — never `int(os.getenv(...))`
- Float env vars: `float(os.getenv(name, "default"))`

### FastAPI Patterns
- Use Pydantic v2 models in `api/schemas.py` for request/response validation
- Keep route handlers thin; business logic in `api/services/`
- Raise `HTTPException(status_code=400, detail="...")` for client errors
- Use `StreamingResponse` for SSE endpoints

## Code Style — TypeScript / React

### Naming & Structure
- Components: `PascalCase.tsx` in `components/` or `pages/`
- Hooks: `useCamelCase.ts` in `hooks/`
- Stores: `kebab-store.ts` using Zustand in `stores/`
- Utility functions: `camelCase` in `lib/`

### React Patterns
- Use functional components with explicit return types: `function Foo(): JSX.Element`
- Custom hooks for reusable logic (e.g., `useThemeStore`)
- Destructure props in function signature
- Use `@tanstack/react-query` for server state

## Key Invariants

- **Vector Store**: Uses `MultimodalQdrantStore` which extends `langchain_qdrant.QdrantVectorStore`. Access via `get_vector_store()` function — never import `vector_store` directly (it's `None` by default).
- **Embedding interface**: `Qwen3VLEmbeddings` implements `langchain_core.embeddings.Embeddings`. Use unified `embed_query(input)` / `embed_documents(inputs)` where `input` can be `str` or `dict` (e.g., `{"text": "...", "image": "..."}`). Supports async via `aembed_query` / `aembed_documents`.
- **Payload structure**: `{page_content: str, metadata: dict, _multimodal_input: dict}`. Metadata fields accessed via `metadata.key` in filters (e.g., `metadata.pdf_name`).
- **Idempotent writes**: Point IDs use `uuid.uuid5` from `(pdf_name, page_idx, chunk_type, text_content[, img_path])` — never `uuid.uuid4()`
- **Image paths**: Probe both `auto/<img_path>` and `auto/images/<img_path>`; store under `"image"` key
- **CUDA/vLLM conflict**: Call `get_vector_store()` inside functions after MinerU parsing completes — never at module level when using `hybrid-auto-engine`
- **Reranking**: Over-fetches `top_k * 3`, reranks, returns `top_k`
- **Score threshold**: Default `0.3`, applied after retrieval, before reranking
- **Tool calling**: Always call at least one tool before answering; use `SystemMessage` for system prompts, never `HumanMessage`
- **Message types**: Use `AIMessage`, `HumanMessage`, `ToolMessage` from `langchain_core.messages`
- **Filters**: Use `qdrant_client.http.models.Filter` with `FieldCondition` — never custom DSL dicts

## Things to Avoid

- Don't commit `.env`, `models/`, `data/`, `qdrant_storage/`
- Don't use `print()` for logging (except streaming output)
- Don't hard-code model paths, API URLs, or credentials
- Don't use deprecated `client.search()` — use `client.query_points(...).points`
- Don't use `HumanMessage` for system prompt — use `SystemMessage`
- Don't hard-code `top_k=5` — read `config.RAG_TOP_K`
- Don't switch `stream_mode` to `"values"` in `query_agent()`
- Don't import `vector_store` at module level — use `get_vector_store()` function
- Don't use `List`, `Dict` from `typing` — use `list`, `dict` (Python 3.9+)
- Don't use custom filter DSL dicts — use `qdrant_client.http.models.Filter`

## Vector Store API

The `MultimodalQdrantStore` class extends `langchain_qdrant.QdrantVectorStore` with multimodal support.

### Initialization

```python
from src.rag.vector_store import get_vector_store

# Get singleton instance (lazy initialization)
store = get_vector_store()
```

### Key Methods

| Method | Description |
|--------|-------------|
| `add_multimodal(inputs, metadatas)` | Store multimodal inputs (text + image) |
| `similarity_search_with_rerank(query, k, filter)` | Search with optional reranking |
| `search_by_image(image_path, instruction)` | Image-based search |
| `fetch_by_metadata(filter)` | Fetch by metadata without vector search |
| `scroll_chunks(filter, limit)` | Paginated chunk retrieval |
| `delete_paper(pdf_name)` | Delete all chunks for a paper |

### Filter Construction

Use `qdrant_client.http.models.Filter` directly:

```python
from qdrant_client.http import models

# Single condition
filter = models.Filter(
    must=[models.FieldCondition(
        key="metadata.pdf_name",
        match=models.MatchValue(value="paper_name")
    )]
)

# Multiple conditions
filter = models.Filter(
    must=[
        models.FieldCondition(key="metadata.pdf_name", match=models.MatchValue(value="paper")),
        models.FieldCondition(key="metadata.chunk_type", match=models.MatchAny(any=["text", "table"])),
    ]
)

# Range condition
filter = models.Filter(
    must=[models.FieldCondition(
        key="metadata.page_idx",
        range=models.Range(gte=0, lte=10)
    )]
)
```

### Hybrid Retrieval

Set `ENABLE_HYBRID=true` in `.env` to enable dense + sparse (BM25) retrieval. Requires `fastembed` package.
