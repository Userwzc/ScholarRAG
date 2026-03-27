import os
import shutil
from dataclasses import dataclass
from typing import Any, Callable, Optional

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

ProgressCallback = Callable[[str, int], None]


def _get_vector_store():
    from src.rag.vector_store import get_vector_store

    return get_vector_store()


def _emit_progress(
    progress_callback: Optional[ProgressCallback],
    stage: str,
    progress: int,
) -> None:
    if progress_callback is None:
        return
    progress_callback(stage, max(0, min(progress, 100)))


def _persist_pdf_for_reader(source_path: str, pdf_name: str) -> None:
    os.makedirs(PDF_STORAGE_DIR, exist_ok=True)
    pdf_dest = os.path.join(PDF_STORAGE_DIR, f"{pdf_name}.pdf")
    if os.path.exists(source_path) and not os.path.exists(pdf_dest):
        shutil.copy(source_path, pdf_dest)


def ingest_paper_file(
    file_path: str,
    save_markdown: bool = False,
    progress_callback: Optional[ProgressCallback] = None,
    paper_version: int = 1,
    is_current: bool = True,
) -> dict[str, Any]:
    from src.core.ingestion import process_paper

    multimodal_inputs, metadata_list, parsed_data = process_paper(
        file_path,
        save_markdown=save_markdown,
        progress_callback=progress_callback,
        paper_version=paper_version,
        is_current=is_current,
    )

    pdf_name = parsed_data.get("pdf_name", "")
    paper_title = parsed_data.get("title", "Unknown Title")
    authors_str = ""

    if metadata_list:
        authors_str = metadata_list[0].get("authors", "")
        paper_title = metadata_list[0].get("title", paper_title)

    _emit_progress(progress_callback, "storing", 65)
    vector_store = _get_vector_store()
    vector_store.add_multimodal(multimodal_inputs, metadata_list)

    _emit_progress(progress_callback, "finalizing", 90)
    _persist_pdf_for_reader(file_path, pdf_name)

    _emit_progress(progress_callback, "completed", 100)
    return {
        "pdf_name": pdf_name,
        "title": paper_title,
        "authors": authors_str,
        "chunk_count": len(multimodal_inputs),
    }


def _build_filter(
    pdf_name: str = "",
    chunk_type: str | None = None,
    paper_version: Optional[int] = None,
) -> Any | None:
    """构建 Qdrant Filter 对象。

    Returns:
        models.Filter 对象，无条件时返回 None
    """
    try:
        from qdrant_client.http import models  # type: ignore[reportMissingImports]
    except ImportError:
        @dataclass
        class _MatchValue:
            value: Any

        @dataclass
        class _FieldCondition:
            key: str
            match: _MatchValue

        @dataclass
        class _Filter:
            must: list[Any]

        class _FallbackModels:
            MatchValue = _MatchValue
            FieldCondition = _FieldCondition
            Filter = _Filter

        models = _FallbackModels()  # type: ignore[assignment]

    must_conditions: list[Any] = []
    if pdf_name:
        must_conditions.append(
            models.FieldCondition(
                key="metadata.pdf_name",
                match=models.MatchValue(value=pdf_name),
            )
        )
    if chunk_type:
        must_conditions.append(
            models.FieldCondition(
                key="metadata.chunk_type",
                match=models.MatchValue(value=chunk_type),
            )
        )
    if paper_version is not None:
        must_conditions.append(
            models.FieldCondition(
                key="metadata.paper_version",
                match=models.MatchValue(value=paper_version),
            )
        )
    return models.Filter(must=must_conditions) if must_conditions else None


def upload_paper(file_path: str) -> PaperUploadResponse:
    result = ingest_paper_file(file_path=file_path, save_markdown=False)

    return PaperUploadResponse(
        pdf_name=result["pdf_name"],
        title=result["title"],
        authors=result["authors"],
        chunk_count=result["chunk_count"],
        message="Paper uploaded and processed successfully",
    )


def list_papers(version: Optional[int] = None) -> list[PaperItem]:
    vector_store = _get_vector_store()
    current_only = version is None
    filter_by_version = _build_filter(paper_version=version)
    all_points = vector_store.get_all_papers(
        filter=filter_by_version,
        current_only=current_only,
    )

    paper_map: dict[str, dict[str, Any]] = {}
    for point in all_points:
        payload = point.get("payload", {})
        meta = payload.get("metadata", {})
        pdf_name = meta.get("pdf_name", "")
        if pdf_name and pdf_name not in paper_map:
            paper_map[pdf_name] = {
                "pdf_name": pdf_name,
                "title": meta.get("title", pdf_name),
                "authors": meta.get("authors", ""),
                "chunk_count": 0,
                "paper_version": meta.get("paper_version"),
                "is_current": meta.get("is_current"),
            }
        if pdf_name:
            paper_map[pdf_name]["chunk_count"] += 1

    papers = list(paper_map.values())
    papers.sort(key=lambda x: x["pdf_name"], reverse=True)

    return [PaperItem(**paper) for paper in papers]


def get_paper_detail(pdf_name: str, version: Optional[int] = None) -> Optional[PaperDetail]:
    vector_store = _get_vector_store()

    qdrant_filter = _build_filter(pdf_name=pdf_name, paper_version=version)
    current_only = version is None
    points, _ = vector_store.scroll_chunks(
        qdrant_filter,
        limit=1,
        current_only=current_only,
    )
    if not points:
        return None

    payload = points[0].get("payload", {})
    meta = payload.get("metadata", {})
    chunk_count = vector_store.count_chunks(qdrant_filter, current_only=current_only)

    return PaperDetail(
        pdf_name=pdf_name,
        title=meta.get("title", pdf_name),
        authors=meta.get("authors", ""),
        chunk_count=chunk_count,
        paper_version=meta.get("paper_version"),
        is_current=meta.get("is_current"),
        metadata={
            "title": meta.get("title"),
            "authors": meta.get("authors"),
            "chunk_type": meta.get("chunk_type"),
            "backend": meta.get("backend"),
            "paper_version": meta.get("paper_version"),
            "is_current": meta.get("is_current"),
        },
    )


def get_paper_chunks(
    pdf_name: str,
    page: int = 1,
    limit: int = 20,
    chunk_type: Optional[str] = None,
    version: Optional[int] = None,
) -> ChunkListResponse:
    vector_store = _get_vector_store()

    qdrant_filter = _build_filter(
        pdf_name=pdf_name,
        chunk_type=chunk_type,
        paper_version=version,
    )
    current_only = version is None
    total = vector_store.count_chunks(qdrant_filter, current_only=current_only)

    all_points, _ = vector_store.scroll_chunks(
        qdrant_filter,
        limit=10000,
        current_only=current_only,
    )

    start = (page - 1) * limit
    end = start + limit
    page_results = all_points[start:end]

    chunks = []
    for point in page_results:
        payload = point.get("payload", {})
        meta = payload.get("metadata", {})
        point_id = point.get("id", "")
        mm_input = payload.get("_multimodal_input", {})

        chunks.append(
            ChunkItem(
                id=str(point_id),
                content=mm_input.get("text", payload.get("page_content", "")),
                chunk_type=meta.get("chunk_type", "text"),
                page_idx=meta.get("page_idx"),
                heading=meta.get("heading"),
                paper_version=meta.get("paper_version"),
                is_current=meta.get("is_current"),
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

    # Delete PDF file
    pdf_path = os.path.join(PDF_STORAGE_DIR, f"{pdf_name}.pdf")
    if os.path.exists(pdf_path):
        os.remove(pdf_path)

    # Delete from vector store and parsed files (manager handles both)
    return manager.delete_paper(pdf_name, delete_from_vector_store=True)


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


def get_paper_toc(pdf_name: str, version: Optional[int] = None) -> Optional[TOCResponse]:
    vector_store = _get_vector_store()

    qdrant_filter = _build_filter(pdf_name=pdf_name, paper_version=version)
    all_points, _ = vector_store.scroll_chunks(
        qdrant_filter,
        limit=10000,
        current_only=version is None,
    )
    if not all_points:
        return None

    toc_items: list[TOCItem] = []
    seen_sections: set[str] = set()
    seen_visuals: set[str] = set()
    max_page = 0

    for point in all_points:
        payload = point.get("payload", {})
        meta = payload.get("metadata", {})
        page_idx = meta.get("page_idx", 0)
        if isinstance(page_idx, int) and page_idx > max_page:
            max_page = page_idx

        chunk_type = meta.get("chunk_type", "text")
        heading = str(meta.get("heading", "") or "").strip()
        section_depth = meta.get("section_depth", 0)

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
            label = meta.get("figure_or_table_label", "")
            caption = str(meta.get("caption", "") or "").strip()
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
