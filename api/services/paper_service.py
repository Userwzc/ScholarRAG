import os
import shutil
from typing import Any, Optional

from api.config import API_UPLOAD_DIR
from api.schemas import (
    ChunkItem,
    ChunkListResponse,
    PaperDetail,
    PaperItem,
    PaperUploadResponse,
    TOCItem,
    TOCResponse,
)
from config.settings import config

PDF_STORAGE_DIR = config.PDF_STORAGE_DIR


def _get_vector_store():
    from src.rag.vector_store import vector_store

    return vector_store


def upload_paper(file_path: str) -> PaperUploadResponse:
    from src.core.ingestion import process_paper

    # Store PDF first (before vector store write)
    os.makedirs(PDF_STORAGE_DIR, exist_ok=True)

    multimodal_inputs, metadata_list, parsed_data = process_paper(
        file_path, save_markdown=False
    )

    pdf_name = parsed_data.get("pdf_name", "")
    paper_title = parsed_data.get("title", "Unknown Title")
    authors_str = ""

    if metadata_list:
        authors_str = metadata_list[0].get("authors", "")
        paper_title = metadata_list[0].get("title", paper_title)

    # Copy original PDF for reader functionality
    pdf_dest = os.path.join(PDF_STORAGE_DIR, f"{pdf_name}.pdf")
    if os.path.exists(file_path) and not os.path.exists(pdf_dest):
        shutil.copy(file_path, pdf_dest)

    # Now write to vector store
    vector_store = _get_vector_store()
    vector_store.store_multimodal_inputs(multimodal_inputs, metadata_list)

    return PaperUploadResponse(
        pdf_name=pdf_name,
        title=paper_title,
        authors=authors_str,
        chunk_count=len(multimodal_inputs),
        message="Paper uploaded and processed successfully",
    )


def list_papers() -> list[PaperItem]:
    vector_store = _get_vector_store()
    all_points = vector_store.get_all_papers()

    paper_map: dict[str, dict[str, Any]] = {}
    for point in all_points:
        payload = point.get("payload", {})
        pdf_name = payload.get("pdf_name", "")
        if pdf_name and pdf_name not in paper_map:
            paper_map[pdf_name] = {
                "pdf_name": pdf_name,
                "title": payload.get("title", pdf_name),
                "authors": payload.get("authors", ""),
                "chunk_count": 0,
            }
        if pdf_name:
            paper_map[pdf_name]["chunk_count"] += 1

    papers = list(paper_map.values())
    papers.sort(key=lambda x: x["pdf_name"], reverse=True)

    return [PaperItem(**paper) for paper in papers]


def get_paper_detail(pdf_name: str) -> Optional[PaperDetail]:
    vector_store = _get_vector_store()

    points, _ = vector_store.scroll_chunks({"pdf_name": pdf_name}, limit=1)
    if not points:
        return None

    payload = points[0].get("payload", {})
    chunk_count = vector_store.count_chunks({"pdf_name": pdf_name})

    return PaperDetail(
        pdf_name=pdf_name,
        title=payload.get("title", pdf_name),
        authors=payload.get("authors", ""),
        chunk_count=chunk_count,
        metadata={
            "title": payload.get("title"),
            "authors": payload.get("authors"),
            "chunk_type": payload.get("chunk_type"),
            "backend": payload.get("backend"),
        },
    )


def get_paper_chunks(
    pdf_name: str,
    page: int = 1,
    limit: int = 20,
    chunk_type: Optional[str] = None,
) -> ChunkListResponse:
    vector_store = _get_vector_store()

    filters = {"pdf_name": pdf_name}
    if chunk_type:
        filters["chunk_type"] = chunk_type

    total = vector_store.count_chunks(filters)

    all_points, _ = vector_store.scroll_chunks(filters, limit=10000)

    start = (page - 1) * limit
    end = start + limit
    page_results = all_points[start:end]

    chunks = []
    for point in page_results:
        payload = point.get("payload", {})
        point_id = point.get("id", "")
        mm_input = payload.get("_multimodal_input", {})

        chunks.append(
            ChunkItem(
                id=str(point_id),
                content=mm_input.get("text", payload.get("page_content", "")),
                chunk_type=payload.get("chunk_type", "text"),
                page_idx=payload.get("page_idx"),
                heading=payload.get("heading"),
                image=mm_input.get("image"),
            )
        )

    return ChunkListResponse(
        chunks=chunks,
        total=total,
        page=page,
        limit=limit,
    )


def delete_paper(pdf_name: str) -> bool:
    from src.ingest.paper_manager import PaperManager

    manager = PaperManager(output_dir="./data/parsed")

    pdf_path = os.path.join(PDF_STORAGE_DIR, f"{pdf_name}.pdf")
    if os.path.exists(pdf_path):
        os.remove(pdf_path)

    return manager.delete_paper(pdf_name)


def save_uploaded_file(file_content: bytes, filename: str) -> str:
    os.makedirs(API_UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(API_UPLOAD_DIR, filename)
    with open(file_path, "wb") as f:
        f.write(file_content)
    return file_path


def cleanup_uploaded_file(file_path: str) -> None:
    if os.path.exists(file_path):
        os.remove(file_path)


def get_pdf_path(pdf_name: str) -> Optional[str]:
    pdf_path = os.path.join(PDF_STORAGE_DIR, f"{pdf_name}.pdf")
    if os.path.exists(pdf_path):
        return pdf_path
    return None


def get_paper_toc(pdf_name: str) -> Optional[TOCResponse]:
    vector_store = _get_vector_store()

    all_points, _ = vector_store.scroll_chunks({"pdf_name": pdf_name}, limit=10000)
    if not all_points:
        return None

    toc_items: list[TOCItem] = []
    seen_sections: set[str] = set()
    seen_visuals: set[str] = set()
    max_page = 0

    for point in all_points:
        payload = point.get("payload", {})
        page_idx = payload.get("page_idx", 0)
        if isinstance(page_idx, int) and page_idx > max_page:
            max_page = page_idx

        chunk_type = payload.get("chunk_type", "text")
        heading = str(payload.get("heading", "") or "").strip()
        section_depth = payload.get("section_depth", 0)

        if chunk_type in ("text", "title") and heading:
            if heading not in seen_sections:
                seen_sections.add(heading)
                toc_items.append(
                    TOCItem(
                        id=f"section-{len(toc_items)}",
                        level=min(section_depth, 4) if section_depth > 0 else 1,
                        text=heading,
                        page_idx=page_idx if isinstance(page_idx, int) else 0,
                        chunk_type="section",
                    )
                )

        if chunk_type in ("image", "table"):
            label = payload.get("figure_or_table_label", "")
            caption = str(payload.get("caption", "") or "").strip()
            visual_text = label or caption or f"{chunk_type.capitalize()}"
            visual_key = f"{chunk_type}-{page_idx}-{visual_text}"

            if visual_key not in seen_visuals and (label or caption):
                seen_visuals.add(visual_key)
                toc_items.append(
                    TOCItem(
                        id=f"{chunk_type}-{len(toc_items)}",
                        level=2,
                        text=visual_text,
                        page_idx=page_idx if isinstance(page_idx, int) else 0,
                        chunk_type=chunk_type,
                    )
                )

    toc_items.sort(key=lambda x: (x.page_idx, x.id))

    return TOCResponse(items=toc_items, total_pages=max_page + 1)
