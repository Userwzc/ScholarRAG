import argparse
import os
import re
import sys
import warnings

os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"

warnings.filterwarnings("ignore", message="Class .* is implemented in both")

from dotenv import load_dotenv  # noqa: E402

# Must be the very first call so .env values override any pre-set system
# environment variables (e.g. MINERU_MODEL_SOURCE) before any module-level
# config singletons are constructed.
load_dotenv(override=True)

from src.ingest.mineru_parser import MinerUParser  # noqa: E402

# NOTE: vector_store and agent_app are intentionally NOT imported at module
# level.  Both load Qwen3VLEmbedder which initialises CUDA immediately.  When
# the `add` subcommand is used, MinerU's hybrid/vlm backend launches a vLLM
# worker subprocess via `spawn`.  vLLM detects CUDA-already-initialised and
# forces spawn mode, but the EngineCore child process then crashes because it
# inherits the parent's CUDA context.  Deferring these imports to after
# parse_pdf() completes avoids the conflict entirely.
from src.utils.logger import get_logger  # noqa: E402
from config.settings import config  # noqa: E402

logger = get_logger(__name__)

INGESTION_SCHEMA_VERSION = 3


def add_paper(pdf_path: str) -> None:
    if not os.path.isfile(pdf_path):
        logger.error("File not found: %s", pdf_path)
        sys.exit(1)
    if not pdf_path.lower().endswith(".pdf"):
        logger.error("Expected a .pdf file, got: %s", pdf_path)
        sys.exit(1)

    logger.info("Adding paper from %s …", pdf_path)

    # Use centralized ingestion logic
    from src.core.ingestion import process_paper
    multimodal_inputs, metadata_list, _ = process_paper(pdf_path, save_markdown=True)

    # Import vector_store only after parse_pdf() has finished and released
    # the vLLM subprocess.  This guarantees CUDA is not yet initialised in
    # this process when vLLM spawns its EngineCore child, avoiding the
    # "EngineCore died unexpectedly" crash.
    from src.rag.vector_store import vector_store  # noqa: E402

    vector_store.store_multimodal_inputs(multimodal_inputs, metadata_list)
    logger.info("Paper added successfully — %d chunks stored.", len(multimodal_inputs))


def query_agent(question: str) -> None:
    from src.agent.graph import stream_answer_events  # noqa: E402

    logger.info("Question: %s", question)
    final_content: list[str] = []

    try:
        for event in stream_answer_events(question):
            event_type = event.get("type", "")

            if event_type == "agent_status":
                phase = event.get("phase", "thinking")
                step = event.get("step", "?")
                text = event.get("text", "")
                print(f"[agent:{phase}:{step}] {text}", flush=True)
            elif event_type == "tool_call":
                tool = event.get("tool", "tool")
                kind = event.get("kind", "tool")
                args = event.get("args", {})
                query_text = args.get("query") if isinstance(args, dict) else None
                page_idx = args.get("page_idx") if isinstance(args, dict) else None
                pdf_name = args.get("pdf_name") if isinstance(args, dict) else None
                labels = {
                    "paper_search": "search-papers",
                    "visual_search": "search-visuals",
                    "page_context": "page-context",
                }
                label = labels.get(kind, tool)
                if query_text:
                    print(f"[{label}] {query_text}", flush=True)
                elif pdf_name is not None and page_idx is not None:
                    print(f"[{label}] {pdf_name}:{page_idx}", flush=True)
                else:
                    print(f"[{label}] {tool}", flush=True)
            elif event_type == "tool_result":
                tool = event.get("tool", "tool")
                kind = event.get("kind", "tool")
                count = event.get("count", 0)
                pages = event.get("pages", [])
                labels = {
                    "paper_search": "search-papers-result",
                    "visual_search": "search-visuals-result",
                    "page_context": "page-context-result",
                }
                label = labels.get(kind, f"{tool}-result")
                page_text = f" on {', '.join(pages[:3])}" if pages else ""
                print(f"[{label}] {count} item(s){page_text}", flush=True)
            elif event_type == "agent_observation":
                step = event.get("step", "?")
                text = event.get("text", "")
                print(f"[agent:observe:{step}] {text}", flush=True)
            elif event_type == "agent_visual_context":
                step = event.get("step", "?")
                count = event.get("count", 0)
                pages = event.get("pages", [])
                page_text = f" from {', '.join(pages[:3])}" if pages else ""
                print(
                    f"[agent:vision:{step}] attached {count} visual(s){page_text}",
                    flush=True,
                )
            elif event_type == "answer_started":
                print("[answer] Streaming final response", flush=True)
                print()
            elif event_type == "answer_token":
                token = event.get("text", "")
                if token:
                    print(token, end="", flush=True)
                    final_content.append(token)
    except Exception as exc:
        logger.error("Agent stream failed: %s", exc, exc_info=True)
        return

    if final_content:
        print()
        logger.debug("Agent answer: %s", "".join(final_content))
    else:
        logger.warning(
            "Final synthesis produced no output — check LLM connectivity and evidence assembly."
        )


def delete_paper(pdf_name: str) -> None:
    """Delete a paper from Qdrant and remove its parsed files."""
    from src.ingest.paper_manager import PaperManager

    logger.info("Deleting paper: %s …", pdf_name)
    manager = PaperManager(output_dir="./data/parsed")
    manager.delete_paper(pdf_name)


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(
        description="Agentic RAG System for Research Papers"
    )
    subparsers = arg_parser.add_subparsers(dest="command")

    parser_add = subparsers.add_parser("add", help="Ingest a PDF into the vector store")
    parser_add.add_argument("pdf_path", type=str, help="Path to the PDF file")

    parser_query = subparsers.add_parser(
        "query", help="Ask a question via the RAG agent"
    )
    parser_query.add_argument("question", type=str, help="Question to ask the agent")

    parser_delete = subparsers.add_parser(
        "delete", help="Delete a paper from vector store and remove parsed files"
    )
    parser_delete.add_argument(
        "pdf_name", type=str, help="PDF file name (without extension)"
    )

    args = arg_parser.parse_args()

    if args.command == "add":
        add_paper(args.pdf_path)
    elif args.command == "query":
        query_agent(args.question)
    elif args.command == "delete":
        delete_paper(args.pdf_name)
    else:
        arg_parser.print_help()
        sys.exit(1)
