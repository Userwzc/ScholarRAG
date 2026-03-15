import argparse
import os
import sys
import warnings

os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"

warnings.filterwarnings("ignore", message="Class .* is implemented in both")

from dotenv import load_dotenv  # noqa: E402

# Must be the very first call so .env values override any pre-set system
# environment variables (e.g. MINERU_MODEL_SOURCE) before any module-level
# config singletons are constructed.
load_dotenv(override=True)

from langchain_core.messages import AIMessageChunk, HumanMessage  # noqa: E402

from src.ingest.mineru_parser import MinerUParser  # noqa: E402
from src.rag.vector_store import vector_store  # noqa: E402
from src.agent.graph import app as agent_app  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402
from config.settings import config  # noqa: E402

logger = get_logger(__name__)


def add_paper(pdf_path: str) -> None:
    if not os.path.isfile(pdf_path):
        logger.error("File not found: %s", pdf_path)
        sys.exit(1)
    if not pdf_path.lower().endswith(".pdf"):
        logger.error("Expected a .pdf file, got: %s", pdf_path)
        sys.exit(1)

    logger.info("Adding paper from %s …", pdf_path)

    # 1. Parse PDF via MinerU
    parser = MinerUParser(output_dir="./data/parsed", backend=config.MINERU_BACKEND)
    parsed_data = parser.parse_pdf(pdf_path)

    # 2. Chunk into typed, structured segments
    chunks_data, doc_metadata = parser.chunk_content(parsed_data)

    # Optionally persist a human-readable reconstruction for debugging
    pdf_name = parsed_data.get("pdf_name", "")
    backend_subdir = parser.backend_subdir
    clean_md_path = os.path.join(
        parser.output_dir, pdf_name, backend_subdir, f"{pdf_name}_clean.md"
    )
    try:
        with open(clean_md_path, "w", encoding="utf-8") as f:
            for chunk in chunks_data:
                f.write(chunk["content"] + "\n\n")
    except Exception as exc:
        logger.error("Could not save markdown reconstruction: %s", exc)

    # 3. Embed and store in Qdrant
    # Use module-level singleton to avoid reloading embedding model

    # Derive the best available title from chunk-level metadata first,
    # then fall back to what the parser recorded in parsed_data.
    paper_title = doc_metadata.get("title_extracted") or parsed_data.get(
        "title", "Unknown Title"
    )

    # Authors: filter pre-abstract blocks to find clean author lines.
    # Heuristics: ≤120 chars, no "@" (email), no known ACM DL page-header tokens.
    _NOISE_TOKENS = (
        "PDF Download",
        "Total Citations",
        "Total Downloads",
        "doi.org",
        "acm.org",
    )
    pre_abstract = doc_metadata.get("pre_abstract_meta", [])
    author_candidates = [
        s
        for s in pre_abstract
        if len(s) <= 120 and "@" not in s and not any(tok in s for tok in _NOISE_TOKENS)
    ]
    authors_str = " | ".join(author_candidates[:3]) if author_candidates else ""

    multimodal_inputs = []
    metadata_list = []

    for chunk in chunks_data:
        meta = {
            "title": paper_title,
            "pdf_name": pdf_name,
            "chunk_type": chunk.get("type", "text"),
            "authors": authors_str,
            "footnotes_count": len(doc_metadata.get("footnotes_and_discarded", [])),
        }
        meta.update(chunk.get("metadata", {}))

        # Build the multimodal input dict for Qwen3-VL
        input_item: dict = {"text": chunk["content"]}

        # Resolve primary image path to absolute, then include in embedding.
        # MinerU writes images into an "images/" subdirectory under the auto
        # output folder, so we probe both the direct path and the subdirectory.
        if meta.get("img_path"):
            backend_dir = os.path.join(parser.output_dir, pdf_name, backend_subdir)
            img_candidates = [
                os.path.join(backend_dir, meta["img_path"]),
                os.path.join(backend_dir, "images", meta["img_path"]),
            ]
            for img_abs in img_candidates:
                if os.path.exists(img_abs):
                    input_item["image"] = img_abs
                    break
            else:
                logger.warning("Image not found for chunk: %s", meta["img_path"])

        # Resolve equation image paths to absolute in metadata (not embedded).
        if meta.get("equation_imgs"):
            backend_dir = os.path.join(parser.output_dir, pdf_name, backend_subdir)
            abs_eq_imgs = []
            for eq_img in meta["equation_imgs"]:
                for candidate in [
                    os.path.join(backend_dir, eq_img),
                    os.path.join(backend_dir, "images", eq_img),
                ]:
                    if os.path.exists(candidate):
                        abs_eq_imgs.append(candidate)
                        break
            meta["equation_imgs"] = abs_eq_imgs

        multimodal_inputs.append(input_item)
        metadata_list.append(meta)

    vector_store.store_multimodal_inputs(multimodal_inputs, metadata_list)
    logger.info("Paper added successfully — %d chunks stored.", len(multimodal_inputs))


def query_agent(question: str) -> None:
    logger.info("Question: %s", question)

    inputs = {
        "messages": [HumanMessage(content=question)],
    }

    # stream_mode="messages" yields (chunk, metadata) pairs, where chunk is a
    # BaseMessageChunk.  We print AI tokens to stdout as they arrive so the
    # user sees a live response rather than waiting for the full answer.
    final_content: list[str] = []
    in_ai_turn = False

    for chunk, metadata in agent_app.stream(inputs, stream_mode="messages"):
        if not isinstance(chunk, AIMessageChunk):
            # Skip tool-call chunks and other internal messages.
            continue
        node = metadata.get("langgraph_node", "")
        if node != "agent":
            # Only stream the agent's final answer, not intermediate tool output.
            continue
        if chunk.tool_call_chunks:
            # Suppress tool-call fragments — not useful as raw text.
            continue
        token = chunk.content if isinstance(chunk.content, str) else ""
        if not token:
            continue
        if not in_ai_turn:
            print()  # blank line before the answer starts
            in_ai_turn = True
        print(token, end="", flush=True)
        final_content.append(token)

    if in_ai_turn:
        print()  # trailing newline after streaming completes
        logger.info("Agent answer: %s", "".join(final_content))


def delete_paper(pdf_name: str) -> None:
    """Delete a paper from Qdrant and remove its parsed files."""
    from src.ingest.paper_manager import PaperManager

    logger.info("Deleting paper: %s …", pdf_name)
    manager = PaperManager()
    manager.delete_paper(pdf_name, parsed_output_dir="./data/parsed")


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
