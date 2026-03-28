# pyright: reportMissingImports=false

import argparse
import os
import sys
import warnings

os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"

warnings.filterwarnings("ignore", message="Class .* is implemented in both")

from dotenv import load_dotenv  # pyright: ignore[reportMissingImports] # noqa: E402
from config.settings import config  # noqa: E402

# Must be the very first call so .env values override any pre-set system
# environment variables (e.g. MINERU_MODEL_SOURCE) before any module-level
# config singletons are constructed.
load_dotenv(override=True)


# NOTE: get_vector_store is intentionally NOT imported at module level.
# Importing it triggers CUDA initialization which conflicts with MinerU's
# hybrid-auto-engine vLLM backend when both are used in the same process.
from src.utils.logger import get_logger  # noqa: E402
from src.utils.exceptions import AppError, ExternalServiceError  # noqa: E402
from src.utils.stream_output import log_status, stream_output  # noqa: E402

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

    # Import vector_store only after parse_pdf() has finished and released
    # the vLLM subprocess.  This guarantees CUDA is not yet initialised in
    # this process when vLLM spawns its EngineCore child, avoiding the
    # "EngineCore died unexpectedly" crash.
    from src.rag.vector_store import get_vector_store  # noqa: E402

    # Use centralized ingestion logic (call once, not twice)
    from src.core.ingestion import process_paper

    multimodal_inputs, metadata_list, _ = process_paper(pdf_path, save_markdown=True)
    get_vector_store().add_multimodal(multimodal_inputs, metadata_list)
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
                log_status(f"[agent:{phase}:{step}] {text}")
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
                    log_status(f"[{label}] {query_text}")
                elif pdf_name is not None and page_idx is not None:
                    log_status(f"[{label}] {pdf_name}:{page_idx}")
                else:
                    log_status(f"[{label}] {tool}")
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
                log_status(f"[{label}] {count} item(s){page_text}")
            elif event_type == "agent_observation":
                step = event.get("step", "?")
                text = event.get("text", "")
                log_status(f"[agent:observe:{step}] {text}")
            elif event_type == "agent_visual_context":
                step = event.get("step", "?")
                count = event.get("count", 0)
                pages = event.get("pages", [])
                page_text = f" from {', '.join(pages[:3])}" if pages else ""
                log_status(
                    f"[agent:vision:{step}] attached {count} visual(s){page_text}"
                )
            elif event_type == "answer_started":
                log_status("[answer] Streaming final response")
                stream_output("")
            elif event_type == "answer_token":
                token = event.get("text", "")
                if token:
                    stream_output(token, end="")
                    final_content.append(token)
    except AppError as exc:
        logger.error("Agent stream failed: %s", exc, exc_info=True)
        return
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        error = ExternalServiceError("Agent stream failed", log_message=str(exc))
        logger.error("%s: %s", error.message, exc, exc_info=True)
        return

    if final_content:
        stream_output("")
        logger.debug("Agent answer: %s", "".join(final_content))
    else:
        logger.warning(
            "Final synthesis produced no output — check LLM connectivity and evidence assembly."
        )


def delete_paper(pdf_name: str) -> None:
    """Delete a paper from Qdrant and remove its parsed file."""
    from src.ingest.paper_manager import PaperManager

    logger.info("Deleting paper: %s …", pdf_name)
    manager = PaperManager(output_dir=config.PARSED_OUTPUT_DIR)
    manager.delete_paper(pdf_name, delete_from_vector_store=True)


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
