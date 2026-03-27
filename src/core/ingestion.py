import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.ingest.mineru_parser import MinerUParser
from config.settings import config
from src.utils.logger import get_logger

logger = get_logger(__name__)

INGESTION_SCHEMA_VERSION = 3

ProgressCallback = Callable[[str, int], None]


def _emit_progress(
    progress_callback: Optional[ProgressCallback],
    stage: str,
    progress: int,
) -> None:
    if progress_callback is None:
        return
    progress_callback(stage, max(0, min(progress, 100)))


def process_paper(
    pdf_path: str,
    save_markdown: bool = True,
    progress_callback: Optional[ProgressCallback] = None,
    paper_version: int = 1,
    is_current: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Parses a PDF, chunks its content, and prepares multimodal inputs and metadatas for vector storage.
    Returns: (multimodal_inputs, metadata_list, parsed_data)
    """
    parser = MinerUParser(output_dir="./data/parsed", backend=config.MINERU_BACKEND)

    _emit_progress(progress_callback, "parsing", 10)
    parsed_data = parser.parse_pdf(pdf_path)

    _emit_progress(progress_callback, "chunking", 35)
    chunks_data, doc_metadata = parser.chunk_content(parsed_data)

    pdf_name = parsed_data.get("pdf_name", "")
    backend_subdir = parser.backend_subdir

    if save_markdown:
        clean_md_path = os.path.join(
            parser.output_dir, pdf_name, backend_subdir, f"{pdf_name}_clean.md"
        )
        try:
            with open(clean_md_path, "w", encoding="utf-8") as f:
                for chunk in chunks_data:
                    f.write(chunk.get("content", "") + "\n\n")
        except Exception as exc:
            logger.error("Could not save markdown reconstruction: %s", exc)

    paper_title = doc_metadata.get("title_extracted") or parsed_data.get(
        "title", "Unknown Title"
    )

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
        meta["paper_version"] = paper_version
        meta["is_current"] = is_current
        meta.setdefault("has_context_embedding", False)

        input_item: dict = {"text": chunk.get("content", "")}

        chunk_type = chunk.get("type", "")
        if chunk_type in ("image", "table"):
            page_idx = meta.get("page_idx")
            if page_idx is not None:
                context_parts: list[str] = []
                for search_page in [page_idx, page_idx - 1]:
                    if search_page < 0:
                        continue
                    if search_page in page_texts:
                        for text_item in page_texts[search_page]:
                            text_content = text_item.get("text", "")
                            if not text_content:
                                continue
                            if re.search(
                                r"\b(Table|Figure|Fig\.?)\s+\d+",
                                text_content,
                                re.IGNORECASE,
                            ):
                                context_parts.append(text_content[:400])
                if context_parts:
                    context_text = "\n[Context] ".join(context_parts)
                    input_item["text"] = (
                        f"[Context] {context_text}\n\n{chunk.get('content', '')}"
                    )
                    meta["has_context_embedding"] = True

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

    return multimodal_inputs, metadata_list, parsed_data
