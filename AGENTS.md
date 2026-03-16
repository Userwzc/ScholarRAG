# AGENTS.md — ScholarRAG Coding Guidelines

## Project Overview

ScholarRAG is a multimodal Retrieval-Augmented Generation (RAG) system for academic papers. It ingests PDFs via MinerU, embeds content with a local Qwen3-VL model, stores vectors in Qdrant, and answers queries through a LangGraph-powered agent backed by an OpenAI-compatible LLM API.

**Language:** Python 3.12  
**Key frameworks:** LangChain / LangGraph, HuggingFace Transformers, Qdrant, MinerU, PyTorch

---

## Project Structure

```
ScholarRAG/
├── main.py                 # CLI entrypoint (add / query / delete subcommands)
├── config/
│   └── settings.py         # Config dataclass; reads .env via dotenv
├── src/
│   ├── agent/
│   │   ├── graph.py        # LangGraph StateGraph definition
│   │   └── tools.py        # @tool: paper_retriever (calls retrieve_papers)
│   ├── custom/
│   │   ├── vision_utils.py         # Shared helpers: is_image_path, is_video_input, sample_frames
│   │   ├── qwen3_vl_embedding.py   # Local Qwen3-VL embedding model
│   │   └── qwen3_vl_reranker.py    # Local Qwen3-VL reranking model
│   ├── ingest/
│   │   ├── mineru_parser.py        # PDF → structured chunks via MinerU
│   │   └── paper_manager.py        # PaperManager: delete_paper lifecycle
│   ├── rag/
│   │   ├── embedding.py            # LangChain-compatible Qwen3VLEmbeddings adapter
│   │   └── vector_store.py         # Qdrant store/search/rerank/delete wrapper
│   └── utils/
│       └── logger.py               # get_logger(__name__) factory
└── data/parsed/            # MinerU output (gitignored)
```

All `__init__.py` files are intentionally empty package markers.

---

## Environment Setup

Uses a **conda environment** named `scholarrag` (Python 3.12). There is no `pyproject.toml` or `requirements.txt`; dependencies are managed directly in the conda env.

```bash
conda activate scholarrag
```

Runtime configuration via `.env` (never commit this file):

| Key | Required | Default | Role |
|---|---|---|---|
| `OPENAI_API_BASE` | yes | — | LLM API endpoint |
| `OPENAI_API_KEY` | yes | — | LLM API key |
| `QDRANT_HOST` | yes | `localhost` | Qdrant host |
| `QDRANT_PORT` | yes | `6333` | Qdrant port |
| `LLM_MODEL` | yes | — | Model name for the agent |
| `EMBEDDING_MODEL` | yes | `models/Qwen3-VL-Embedding-2B` | Local embedding model path |
| `MINERU_MODEL_SOURCE` | yes | `modelscope` | MinerU model source |
| `MINERU_BACKEND` | no | `pipeline` | MinerU backend (`pipeline` or `hybrid-auto-engine`) |
| `RERANKER_MODEL` | no | `""` | Local reranker path; empty = disabled |
| `RAG_TOP_K` | no | `5` | Chunks returned per retriever call |
| `SCORE_THRESHOLD` | no | `0.3` | Min cosine similarity; `0.0` disables |
| `AGENT_MAX_ITERATIONS` | no | `10` | LangGraph recursion limit |
| `LOG_LEVEL` | no | `INFO` | Logger verbosity |

---

## Build / Run Commands

No build step. Run the CLI directly:

```bash
# Ingest a PDF paper
python main.py add <path/to/paper.pdf>

# Query the RAG agent
python main.py query "<your question here>"

# Delete a paper from the vector store and remove parsed files
python main.py delete <pdf_name_without_extension>
```

---

## Linting and Formatting

`ruff` (v0.15+) is the only linting/formatting tool. No project-level `ruff.toml` exists.

```bash
ruff check .           # lint
ruff check --fix .     # auto-fix
ruff format .          # format
```

Do not introduce mypy, black, isort, or pylint.

### E402 in main.py

`load_dotenv(override=True)` must be called before all other imports so `.env` values reach `config/settings.py` at module-construction time. All subsequent imports carry `# noqa: E402`. **Do not reorder these imports.**

### Known LSP false positives (do not fix)

- `Qwen3VLConfig`, `ModelOutput`, `TransformersKwargs` "not exported" — HuggingFace stub mismatch
- `Qwen3VLProcessor.tokenizer` unknown attribute — same cause
- `add_generation_prompt`, `tokenize`, `video_metadata`, etc. not in processor stubs
- `device` not assignable to model `__call__` — stub issue, works at runtime
- Qdrant stubs strict about `None` for optional params — harmless
- `ChatOpenAI` params (`openai_api_base`, `openai_api_key`, `model_name`) flagged unknown — runtime API accepts them
- `Score < 0.35` in a string literal flagged as type annotation — harmless
- `stream()` argument `dict` vs `AgentState` — LangGraph TypedDict stub issue

---

## Testing

**No automated tests exist.** No `tests/` directory, pytest config, or CI pipeline.

When adding tests, use `pytest`:

```bash
pytest                                              # run all tests
pytest tests/test_vector_store.py                  # run one file
pytest tests/test_vector_store.py::test_upsert     # run one function
pytest -v tests/                                   # verbose
```

Place test files under `tests/`, named `test_<module>.py`, mirroring the `src/` layout.

---

## Code Style Guidelines

### Imports

- Order: **stdlib → third-party → local**, separated by blank lines.
- Cross-package: absolute imports from project root (`from config.settings import config`).
- Within a sub-package: relative imports (`from .embedding import Qwen3VLEmbeddings`).
- Never import inside function bodies unless guarding an optional heavy dependency (e.g. `MinerU`, `PaperManager`).

### Type Annotations

- Annotate all function signatures (parameters and return types).
- Prefer Python 3.9+ built-in generics (`list[str]`, `dict[str, Any]`); do not mix with `typing.List` within a file.
- Use `X | None` or `Optional[X]` for nullable types; be consistent within a file.
- LangGraph state schemas → `TypedDict`. Tool input schemas → Pydantic `BaseModel`.

### Naming Conventions

| Entity | Convention | Example |
|---|---|---|
| Classes | `PascalCase` | `PaperVectorStore`, `MinerUParser` |
| Functions / methods | `snake_case` | `parse_pdf`, `embed_query` |
| Module-level constants | `UPPER_SNAKE_CASE` | `MAX_LENGTH`, `GENERATION_SUFFIX_LEN` |
| Private helpers | `_snake_case` | `_ensure_collection`, `_pooling_last` |
| Loggers | always `logger` | `logger = get_logger(__name__)` |
| Config singleton | `config` | imported from `config.settings` |

### Error Handling

- Catch specific exceptions; avoid bare `except:`.
- Log before re-raising or returning a fallback: `logger.error("Failed: %s", exc)`.
- `ValueError` for bad argument combinations, `TypeError` for wrong types, `FileNotFoundError` for missing paths.
- Optional heavy dependencies use an availability-flag pattern:
  ```python
  try:
      from mineru import something
      MINERU_AVAILABLE = True
  except ImportError:
      MINERU_AVAILABLE = False
  ```

### Logging

Never use `print()` for diagnostics — always use the logger factory:

```python
from src.utils.logger import get_logger
logger = get_logger(__name__)

logger.info("Processing %s", path)      # %-style, not f-strings
logger.warning("Fallback: %s", reason)
logger.error("Failed: %s", exc)
```

Exception: `query_agent()` in `main.py` uses `print()` specifically to stream the answer to the terminal.

### PyTorch / Inference

- Decorate all inference methods with `@torch.no_grad()`.
- Move tensors to `self.device` before forward passes.
- Call `model.eval()` on load; never call `model.train()`.

### Configuration

- All tuneable values live in `config/settings.py` on the `Config` dataclass.
- Integer env vars: use `_parse_int_env(name, default)` — never `int(os.getenv(...))`.
- Float env vars: `float(os.getenv("KEY", "default"))`.
- Read via the `config` singleton; never access `os.environ` outside `settings.py`.

---

## Key Behaviours and Invariants

### Idempotent Writes

`store_multimodal_inputs` derives Qdrant point IDs via `uuid.uuid5` (`_content_uuid`) from `(pdf_name, page_idx, chunk_type, text_content[, img_path])`. Re-ingesting the same PDF overwrites existing points. **Never replace `_content_uuid` with `uuid.uuid4()`.**

### Image Path Resolution

MinerU places images at `data/parsed/<pdf_name>/auto/images/<hash>.jpg`. `add_paper()` probes both `auto/<img_path>` and `auto/images/<img_path>`. Maintain this dual-probe pattern for all new image-handling code. Store the resolved path under the `"image"` key (singular) in the `_multimodal_input` dict.

### CUDA / vLLM Subprocess Conflict (`add` subcommand)

When `MINERU_BACKEND` is set to `hybrid-auto-engine` or `vlm-auto-engine`, MinerU's `do_parse` spawns a **vLLM worker subprocess** to run the VLM model. vLLM requires CUDA to **not yet be initialised** in the parent process when it creates the subprocess; if CUDA is already active it forces `spawn` mode and the EngineCore child crashes with `EngineCore died unexpectedly`.

`vector_store` and `agent_app` both load `Qwen3VLEmbedder` at import time, which immediately initialises CUDA. To avoid the conflict:

- `vector_store` is imported **inside `add_paper()`**, after `parse_pdf()` returns (vLLM subprocess has already exited).
- `agent_app` is imported **inside `query_agent()`**.
- **Never move these two imports back to module level** — that will silently re-introduce the crash whenever `hybrid-auto-engine` or `vlm-auto-engine` is used.

`MinerUParser.parse_pdf()` also sets `MINERU_MODEL_SOURCE` from `config` before calling `do_parse()` if it is not already set in the environment, mirroring what the MinerU CLI does.

### MinerU Backend and Idempotency

`MinerUParser` accepts a `backend` arg (`"pipeline"` or `"hybrid-auto-engine"`). `parse_pdf()` is idempotent: if `<pdf_name>_middle.json` already exists the parse step is skipped. The `code` block type is only emitted by the VLM / hybrid-auto-engine backend.



When `RERANKER_MODEL` is set, `search_similar()` over-fetches `top_k * 3` candidates and re-scores them before returning `top_k`. Pass `rerank=False` to skip for a specific call. `store.rerank(query, results)` is also available directly.

### Score Threshold Filtering

Applied after Qdrant retrieval, before reranking. Default: `config.SCORE_THRESHOLD` (`0.3`). Pass `score_threshold=0.0` to bypass on a specific call.

### Authors Extraction

`doc_metadata["pre_abstract_meta"]` may contain PDF-source noise. The `_NOISE_TOKENS` tuple in `main.py` filters these. Extend `_NOISE_TOKENS` for new paper sources; do not duplicate the filter logic.

### Retrieval Context Format

Each chunk surfaced to the LLM includes a structured header so the agent can cite sources:

```
[Paper: <title>
  File: <pdf_name>.pdf
  Authors: <authors>
  Page: <page_idx>
  Type: <chunk_type>
  Score: <score>]
<chunk text>
```

### Streaming Output

`query_agent()` uses `stream_mode="messages"`. The loop filters to `AIMessageChunk` from the `"agent"` node only, skips tool-call fragments, and flushes each token immediately. **Do not switch to `stream_mode="values"`.**

### LangGraph Agent

- `AgentState` has one field: `messages: Annotated[List[BaseMessage], operator.add]`. Remove dead fields promptly.
- The recursion limit is applied via `app.with_config(recursion_limit=config.AGENT_MAX_ITERATIONS)` after `compile()`.
- The system prompt is a `SystemMessage` (not `HumanMessage`). Keep its three sections (retrieval rules, answer rules, scope) intact.

### Shared Vision Utilities

`is_image_path`, `is_video_input`, `sample_frames` live in `src/custom/vision_utils.py`. Do not duplicate them.

---

## Key Dependencies

| Package | Version | Role |
|---|---|---|
| `torch` | 2.8.0 | Local model inference |
| `transformers` | 4.57.6 | Qwen3-VL model loading |
| `langchain` | 1.2.12 | RAG primitives |
| `langgraph` | 1.1.2 | Agent state machine |
| `qdrant-client` | 1.17.1 | Vector database |
| `mineru` | 2.7.6 | PDF parsing |
| `pydantic` | 2.11.10 | Schema validation |
| `ruff` | 0.15.6 | Linting / formatting |

---

## Things to Avoid

- Do **not** commit `.env`, `models/`, `data/`, or `qdrant_storage/` (all gitignored).
- Do **not** use `print()` for logging — use `logger` (except for terminal streaming in `query_agent()`).
- Do **not** hard-code model paths, API URLs, or credentials in source files.
- Do **not** import inside functions unless guarding an optional dependency. Acceptable exceptions in `main.py`: `MinerU`, `PaperManager`, and critically `vector_store` / `agent_app` — see below.
- Do **not** duplicate vision helpers — import from `src/custom/vision_utils.py`.
- Do **not** add dead fields to `AgentState`.
- Do **not** use `client.search()` (deprecated in qdrant-client ≥ 1.7) — use `client.query_points(...).points`.
- Do **not** replace `_content_uuid` with `uuid.uuid4()`.
- Do **not** inject the system prompt as a `HumanMessage` — use `SystemMessage`.
- Do **not** hard-code `top_k=5` in `tools.py` — read `config.RAG_TOP_K`.
- Do **not** switch `stream_mode` to `"values"` in `query_agent()`.
- Do **not** introduce new top-level dependencies without updating the conda env and documenting them here.
- Do **not** add new `Config` fields using `int(os.getenv(...))` — use `_parse_int_env`.
