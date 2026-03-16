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

    # Build page_idx → text chunks index for context enrichment
    page_texts: dict[int, list[dict[str, str]]] = {}
    for chunk in chunks_data:
        if chunk.get("type") == "text":
            page_idx = chunk.get("metadata", {}).get("page_idx")
            if page_idx is not None:
                if page_idx not in page_texts:
                    page_texts[page_idx] = []
                page_texts[page_idx].append(
                    {
                        "heading": chunk.get("metadata", {}).get("heading", ""),
                        "text": chunk.get("content", ""),
                    }
                )

    multimodal_inputs = []
    metadata_list = []

    for chunk in chunks_data:
        heading = str(chunk.get("metadata", {}).get("heading", "") or "")
        section_root = heading.split(" > ", 1)[0] if heading else ""
        meta = {
            "title": paper_title,
            "title_normalized": paper_title.casefold(),
            "pdf_name": pdf_name,
            "chunk_type": chunk.get("type", "text"),
            "authors": authors_str,
            "authors_normalized": authors_str.casefold(),
            "footnotes_count": len(doc_metadata.get("footnotes_and_discarded", [])),
            "references_count": len(doc_metadata.get("references", [])),
            "pre_abstract_count": len(doc_metadata.get("pre_abstract_meta", [])),
            "backend": parser.backend,
            "ingestion_schema_version": INGESTION_SCHEMA_VERSION,
            "section_root": section_root,
        }
        meta.update(chunk.get("metadata", {}))
        meta.setdefault("has_context_embedding", False)

        # Build the multimodal input dict for Qwen3-VL
        input_item: dict = {"text": chunk["content"]}

        # For image/table chunks, enrich embedding with nearby page context
        # (helps when caption is missing or OCR fails)
        chunk_type = chunk.get("type", "")
        if chunk_type in ("image", "table"):
            page_idx = meta.get("page_idx")
            if page_idx is not None:
                context_parts: list[str] = []
                # Search current page and previous page (Table/Figure often referenced on previous page)
                for search_page in [page_idx, page_idx - 1]:
                    if search_page < 0:
                        continue
                    if search_page in page_texts:
                        for text_item in page_texts[search_page]:
                            text_content = text_item.get("text", "")
                            if not text_content:
                                continue
                            # Match Table/Figure references like "Table 3", "Figure 2", "Fig. 1"
                            if re.search(
                                r"\b(Table|Figure|Fig\.?)\s+\d+",
                                text_content,
                                re.IGNORECASE,
                            ):
                                context_parts.append(text_content[:400])
                if context_parts:
                    context_text = "\n[Context] ".join(context_parts)
                    input_item["text"] = (
                        f"[Context] {context_text}\n\n{chunk['content']}"
                    )
                    meta["has_context_embedding"] = True

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

        meta["has_image"] = bool(input_item.get("image")) or bool(meta.get("img_path"))
        meta["has_caption"] = bool(meta.get("caption"))
        meta["has_footnote"] = bool(meta.get("footnote"))
        meta["has_equation_images"] = bool(meta.get("equation_imgs")) or bool(
            meta.get("has_equation_images")
        )

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
