# AGENTS.md — ScholarRAG Coding Guidelines

## Project Overview

ScholarRAG is a multimodal Retrieval-Augmented Generation (RAG) system for academic papers. It ingests PDFs via MinerU, embeds content with a local Qwen3-VL model, stores vectors in Qdrant, and answers queries through a LangGraph-powered agent backed by an OpenAI-compatible LLM API.

**Language:** Python 3.12  
**Key frameworks:** LangChain / LangGraph, HuggingFace Transformers, Qdrant, MinerU, PyTorch

---

## Project Structure

```
ScholarRAG/
├── main.py              # CLI entrypoint (add / query subcommands)
├── config/
│   └── settings.py      # Central Config dataclass; reads .env via dotenv
├── src/
│   ├── agent/
│   │   ├── graph.py     # LangGraph StateGraph definition
│   │   └── tools.py     # LangChain @tool: retrieve_papers
│   ├── custom/
│   │   ├── vision_utils.py         # Shared vision helpers: is_image_path, is_video_input, sample_frames
│   │   ├── qwen3_vl_embedding.py   # Local Qwen3-VL embedding model
│   │   └── qwen3_vl_reranker.py    # Local Qwen3-VL reranking model
│   ├── ingest/
│   │   └── mineru_parser.py        # PDF → structured chunks via MinerU
│   ├── rag/
│   │   ├── embedding.py            # LangChain-compatible embeddings adapter
│   │   └── vector_store.py         # Qdrant store/search/rerank wrapper
│   └── utils/
│       └── logger.py               # Logging factory: get_logger(__name__)
└── data/parsed/         # MinerU output (gitignored)
```

All `__init__.py` files are intentionally empty package markers.

---

## Environment Setup

The project uses a **conda environment** named `scholarrag` (Python 3.12). There is no `pyproject.toml`; dependencies are tracked in `requirements.txt`.

```bash
# Activate the environment
conda activate scholarrag

# Runtime configuration via .env (never commit this file)
# Required keys: OPENAI_API_BASE, OPENAI_API_KEY, QDRANT_HOST, QDRANT_PORT,
#                LLM_MODEL, MINERU_MODEL_SOURCE, EMBEDDING_MODEL
# Optional keys: RERANKER_MODEL (leave empty to disable reranking)
#                RAG_TOP_K, SCORE_THRESHOLD, AGENT_MAX_ITERATIONS
```

---

## Build / Run Commands

There is no build step. Run the CLI directly:

```bash
# Ingest a PDF paper into the vector store
python main.py add <path/to/paper.pdf>

# Query the RAG agent
python main.py query "<your question here>"
```

---

## Linting and Formatting

`ruff` (v0.15+) is installed in the conda environment. There is no project-level `ruff.toml`, so sane defaults apply:

```bash
# Lint
ruff check .

# Auto-fix lint issues
ruff check --fix .

# Format
ruff format .
```

There is no mypy, black, isort, or pylint configuration. Do not introduce new linting tools without updating this file.

### E402 in main.py

`main.py` intentionally places `load_dotenv(override=True)` before all other imports so that `.env` values reach `config/settings.py` at module-construction time. All subsequent imports carry `# noqa: E402` to suppress the ruff warning. **Do not reorder these imports.**

### Known LSP false positives (do not fix)

The following diagnostics appear in `qwen3_vl_embedding.py` and `qwen3_vl_reranker.py` and are HuggingFace type-stub mismatches — the code runs correctly at runtime:

- `Qwen3VLConfig`, `ModelOutput`, `TransformersKwargs` "not exported" from their modules
- `Qwen3VLProcessor.tokenizer` unknown attribute
- `add_generation_prompt`, `tokenize`, `video_metadata`, `truncation`, `padding`, `do_resize`, `return_tensors` not in processor type stubs
- `device` not assignable to model `__call__` parameter

In `vector_store.py`, Qdrant stubs are strict about `None` for optional parameters — also harmless false positives.

In `graph.py`, `ChatOpenAI` parameter names (`openai_api_base`, `openai_api_key`, `model_name`) are flagged as unknown by the stub — the runtime API accepts them correctly.

In `graph.py`, the LSP flags line 55 of the system prompt string (`Score < 0.35`) as a type annotation error because `<` appears in a string literal — harmless false positive.

In `main.py`, the `stream()` argument type mismatch (`dict` vs `AgentState`) is a LangGraph TypedDict stub issue — runtime works correctly.

---

## Testing

**There are currently no automated tests.** No `tests/` directory, no pytest configuration, and no CI pipeline exist.

When adding tests, use `pytest`:

```bash
# Run all tests
pytest

# Run a single test file
pytest tests/test_vector_store.py

# Run a single test function
pytest tests/test_vector_store.py::test_upsert_and_search

# Run with verbose output
pytest -v tests/
```

Place test files under `tests/` and name them `test_<module>.py`. Mirror the `src/` layout when testing internal modules.

---

## Code Style Guidelines

### Imports

- Order: **standard library → third-party → local**, separated by blank lines.
- Use **absolute imports** from the project root for cross-package imports:
  ```python
  from config.settings import config
  from src.rag.vector_store import PaperVectorStore
  ```
- Use **relative imports** only within the same sub-package:
  ```python
  # inside src/rag/
  from .embedding import Qwen3VLEmbeddings
  ```
- Avoid placing `import` statements inside function bodies unless guarding an optional heavy dependency (MinerU / reranker pattern).

### Type Annotations

- Annotate **all** function signatures (parameters and return types).
- Prefer **Python 3.9+ built-in generics** (`list[str]`, `dict[str, Any]`) over `typing.List` / `typing.Dict`. However, do not break existing code that uses the older style.
- Use `typing.Optional[X]` or `X | None` for nullable types (be consistent within a file).
- Use `TypedDict` for LangGraph state schemas and Pydantic `BaseModel` for tool input schemas.

```python
# Preferred new style
def embed_documents(self, texts: list[str]) -> list[list[float]]:
    ...

# Acceptable legacy style (do not mix within a file)
from typing import List
def embed_documents(self, texts: List[str]) -> List[List[float]]:
    ...
```

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

- Catch specific exceptions whenever possible; avoid bare `except:`.
- Log errors before re-raising or returning a fallback:
  ```python
  try:
      result = do_something()
  except Exception as e:
      logger.error(f"Failed to do something: {e}")
      return fallback_value
  ```
- Raise `ValueError` for bad argument combinations, `TypeError` for wrong input types, `FileNotFoundError` for missing paths — with descriptive messages.
- Use the availability-flag pattern for optional heavy dependencies:
  ```python
  try:
      from mineru import something
      MINERU_AVAILABLE = True
  except ImportError:
      MINERU_AVAILABLE = False
  ```

### Logging

Always use the project logger factory — never `print()` for diagnostics:

```python
from src.utils.logger import get_logger
logger = get_logger(__name__)

logger.info("Processing %s", path)
logger.warning("Fallback triggered: %s", reason)
logger.error("Failed: %s", exc)
```

### PyTorch / Inference

- Decorate all inference methods with `@torch.no_grad()`.
- Move tensors to `self.device` explicitly before forward passes.
- Use `model.eval()` on load; do not call `model.train()` in this codebase.

### LangGraph Agents

- Define agent state as a `TypedDict` with `Annotated[list, operator.add]` for the message field.
- `AgentState` should only contain fields that are actually read or written by graph nodes — remove dead fields promptly.
- Wire graphs with explicit `add_node` / `add_edge` / `add_conditional_edges` — do not use magic graph-building shortcuts.
- Tool schemas must use Pydantic `BaseModel` paired with the `@tool` decorator and an `args_schema` argument.
- In `should_continue`, always cast the last message to `AIMessage` before accessing `.tool_calls`.

### LangChain Tools

```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class MyToolInput(BaseModel):
    query: str = Field(description="The search query")

@tool("my_tool", args_schema=MyToolInput)
def my_tool(query: str) -> str:
    """One-line description used by the LLM."""
    ...
```

### Configuration

- All tuneable values live in `config/settings.py` as fields on the `Config` dataclass.
- Integer env vars must be parsed with `_parse_int_env(name, default)` — never `int(os.getenv(...))` directly.
- Float env vars must be cast explicitly: `float(os.getenv("KEY", "default"))`.
- Read config via the `config` singleton — never use `os.environ` directly outside `settings.py`.
- Secrets go in `.env` only; never hard-code API keys or hostnames.

**Current tuneable knobs (all settable via `.env`):**

| Key | Default | Role |
|---|---|---|
| `RAG_TOP_K` | `5` | Chunks returned to the LLM per retriever call |
| `SCORE_THRESHOLD` | `0.3` | Minimum cosine similarity to keep a chunk; set `0.0` to disable |
| `AGENT_MAX_ITERATIONS` | `10` | LangGraph recursion limit (node visits, not tool calls) |
| `RERANKER_MODEL` | `""` | Path to local reranker; empty = disabled |

### Idempotent Writes (vector_store.py)

`store_paper_chunks` and `store_multimodal_inputs` derive Qdrant point IDs from content using `uuid.uuid5` (`_content_uuid` helper) rather than random UUIDs. This makes `upsert` idempotent: re-ingesting the same PDF overwrites existing points instead of creating duplicates.

The ID is derived from `(pdf_name, page_idx, chunk_type, text_content[, img_path])`. Do **not** replace `_content_uuid` with `uuid.uuid4()` — that will silently reintroduce duplicate accumulation on every `add` run.

### Image Path Resolution (main.py)

MinerU writes image files into an `images/` subdirectory under the `auto/` output folder:

```
data/parsed/<pdf_name>/auto/images/<hash>.jpg
```

`add_paper()` probes both `auto/<img_path>` and `auto/images/<img_path>` when resolving `img_path` from chunk metadata. This dual-probe pattern must be maintained for any new image-handling code. The resolved absolute path is stored under the `"image"` key in the `_multimodal_input` dict (singular, not `"images"`), which is what the Qwen3-VL embedding model reads via `ele.get("image")`.

### Authors Extraction (main.py)

Pre-abstract metadata blocks (`doc_metadata["pre_abstract_meta"]`) often contain page-header noise from PDF sources (e.g. ACM DL: `"PDF Download"`, `"Total Citations"`, `"Total Downloads"`). The author heuristic filters these out with `_NOISE_TOKENS` in addition to the length and `@` checks. When adding support for new paper sources, extend `_NOISE_TOKENS` rather than duplicating the filter logic.

### Reranker (optional)

`PaperVectorStore` lazily loads `Qwen3VLReranker` at init time if `config.RERANKER_MODEL` is non-empty. When loaded:

- `search_similar()` over-fetches `top_k * 3` candidates from Qdrant and re-scores them before returning `top_k`.
- Pass `rerank=False` to `search_similar()` to skip reranking for a specific call.
- `store.rerank(query, results)` is also available as a public method for direct use.

Set `RERANKER_MODEL=` (empty) in `.env` to disable reranking entirely.

### Shared Vision Utilities

All vision-preprocessing helpers (`is_image_path`, `is_video_input`, `sample_frames`) live in `src/custom/vision_utils.py`. Import from there — do not duplicate them in embedding or reranker modules.

### LangGraph Agent System Prompt (graph.py)

The system prompt is injected as a `SystemMessage` (not `HumanMessage`) so that OpenAI-compatible LLMs treat it with system-role authority. It has three sections:

- **Retrieval rules** — always call `paper_retriever` before answering; issue multiple focused sub-queries for multi-part questions; retry with a rephrased query if initial results score below 0.35.
- **Answer rules** — base answers strictly on retrieved chunks; cite sources as `(Author(s), Page N)` or `(PDF: <pdf_name>, Page N)`; no fabrication.
- **Scope** — if the question is entirely unrelated to research papers, acknowledge the limitation.

When editing the system prompt, keep these three sections intact. Do not revert the injection point to `HumanMessage`.

### Score Threshold Filtering (vector_store.py)

`search_similar()` accepts an optional `score_threshold` parameter (float, 0–1). Chunks whose cosine similarity falls below this value are discarded before reranking or returning, preventing low-relevance noise from reaching the LLM.

- Default comes from `config.SCORE_THRESHOLD` (env: `SCORE_THRESHOLD`, default `0.3`).
- Pass `score_threshold=0.0` on a specific call to bypass filtering entirely.
- The threshold is applied **after** Qdrant retrieval and **before** the reranker, so the reranker only sees already-filtered candidates.

### Retrieval Context Format (tools.py)

Each chunk surfaced to the LLM by `paper_retriever` includes a structured header:

```
[Paper: <title>
  File: <pdf_name>.pdf
  Authors: <authors>
  Page: <page_idx>
  Type: <chunk_type>
  Score: <score>]
<chunk text>
```

This gives the LLM the metadata it needs to write accurate citations. Do not strip these fields when modifying the formatter — the system prompt instructs the LLM to use them.

### Streaming Output (main.py)

`query_agent()` uses `stream_mode="messages"` so that AI tokens are printed to `stdout` as they are generated rather than after full completion. The streaming loop:

- Filters to `AIMessageChunk` objects from the `"agent"` node only.
- Skips tool-call fragments (raw JSON tool invocations are not useful as printed output).
- Prints each text token immediately with `print(token, end="", flush=True)`.
- Logs the complete answer via `logger.info` after the stream ends.

Do **not** switch back to `stream_mode="values"` — that blocks until the full response is ready and produces no live output.

### Comments and Docstrings

- Write docstrings for public classes and non-trivial methods.
- Inline comments in either English or Chinese are acceptable (the codebase uses both).
- Prefer descriptive variable names over explanatory comments for obvious operations.

---

## Key Dependencies and Versions

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
- Do **not** call `print()` for logging — use `logger`. Exception: `query_agent()` in `main.py` uses `print()` specifically to stream the answer to the user's terminal.
- Do **not** hard-code model paths, API URLs, or credentials in source files.
- Do **not** import inside functions unless guarding an optional dependency.
- Do **not** duplicate vision helpers — use `src/custom/vision_utils.py`.
- Do **not** add dead fields to `AgentState` — only include what graph nodes actually use.
- Do **not** use `client.search()` (deprecated in qdrant-client ≥ 1.7) — use `client.query_points(...).points`.
- Do **not** replace `_content_uuid` with `uuid.uuid4()` — that silently reintroduces duplicate accumulation on every `add` run.
- Do **not** inject the system prompt as a `HumanMessage` — use `SystemMessage` so LLMs honour its higher authority.
- Do **not** call `workflow.compile()` without `recursion_limit` — an unbounded graph can loop indefinitely. Use `config.AGENT_MAX_ITERATIONS`.
- Do **not** hard-code `top_k=5` in `tools.py` — read `config.RAG_TOP_K` so it is tunable without code changes.
- Do **not** switch `stream_mode` back to `"values"` in `query_agent()` — that suppresses live token output.
- Do **not** introduce new top-level dependencies without updating the conda env and documenting them here.
