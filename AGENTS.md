# AGENTS.md — ScholarRAG Coding Guidelines

## Project Overview

Multimodal RAG system for academic papers: PDFs → MinerU → Qwen3-VL embedding → Qdrant → LangGraph agent → LLM.

**Language:** Python 3.12  
**Key frameworks:** LangChain / LangGraph, HuggingFace Transformers, Qdrant, MinerU, PyTorch

## Project Structure

```
ScholarRAG/
├── main.py                 # CLI: add/query/delete subcommands
├── config/settings.py      # Config dataclass; reads .env
├── src/
│   ├── agent/              # LangGraph: graph.py, tools.py
│   ├── custom/             # vision_utils.py, qwen3_vl_embedding.py, qwen3_vl_reranker.py
│   ├── ingest/             # mineru_parser.py, paper_manager.py
│   ├── rag/                # embedding.py, vector_store.py
│   └── utils/              # logger.py
└── data/parsed/            # MinerU output (gitignored)
```

## Environment

```bash
conda activate scholarrag
```

`.env` (never commit): `OPENAI_API_BASE`, `OPENAI_API_KEY`, `QDRANT_HOST`, `QDRANT_PORT`, `LLM_MODEL`, `EMBEDDING_MODEL`, `MINERU_MODEL_SOURCE`, `MINERU_BACKEND`, `RERANKER_MODEL`, `RAG_TOP_K`, `SCORE_THRESHOLD`, `AGENT_MAX_ITERATIONS`, `LOG_LEVEL`

## Run Commands

```bash
python main.py add <path/to/paper.pdf>   # Ingest PDF
python main.py query "<question>"        # Query RAG agent
python main.py delete <pdf_name>         # Remove paper
```

## Lint / Test

```bash
ruff check .           # lint
ruff check --fix .     # auto-fix
ruff format .          # format

pytest                           # run all tests
pytest tests/test_file.py       # run one file
pytest tests/test_file.py::test_func  # run one function
```

Place tests in `tests/test_<module>.py`.

## Code Style

### Imports
- Order: stdlib → third-party → local (blank lines between)
- Cross-package: `from config.settings import config`
- Within package: `from .embedding import X`
- Never import inside functions except for optional heavy deps (MinerU, PaperManager, vector_store, agent_app)

### Types & Naming
- Annotate all function signatures
- Python 3.9+ generics: `list[str]`, `dict[str, Any]`
- Classes: `PascalCase` | Functions: `snake_case` | Constants: `UPPER_SNAKE_CASE` | Loggers: `logger`

### Error Handling
- Catch specific exceptions; avoid bare `except:`
- Log before re-raising: `logger.error("Failed: %s", exc)`
- `ValueError` for bad args, `TypeError` for wrong types, `FileNotFoundError` for missing paths

### Logging
- Use `get_logger(__name__)` — never `print()` except for streaming in `query_agent()`

### PyTorch
- `@torch.no_grad()` on inference methods
- Move tensors to `self.device`
- Call `model.eval()` on load

### Configuration
- All tunable values in `config/settings.py`
- Integer env vars: `_parse_int_env(name, default)` — never `int(os.getenv(...))`

## Key Invariants

- **Idempotent writes**: Point IDs use `uuid.uuid5` from `(pdf_name, page_idx, chunk_type, text_content[, img_path])` — never `uuid.uuid4()`
- **Image paths**: Probe both `auto/<img_path>` and `auto/images/<img_path>`; store under `"image"` key
- **CUDA/vLLM conflict**: Import `vector_store` inside `add_paper()`, `agent_app` inside `query_agent()` — never at module level when using `hybrid-auto-engine`
- **Reranking**: Over-fetches `top_k * 3`, reranks, returns `top_k`
- **Score threshold**: Default `0.3`, applied after retrieval, before reranking

## Things to Avoid

- Don't commit `.env`, `models/`, `data/`, `qdrant_storage/`
- Don't use `print()` for logging
- Don't hard-code model paths, API URLs, or credentials
- Don't use deprecated `client.search()` — use `client.query_points(...).points`
- Don't use `HumanMessage` for system prompt — use `SystemMessage`
- Don't hard-code `top_k=5` — read `config.RAG_TOP_K`
- Don't switch `stream_mode` to `"values"` in `query_agent()`
