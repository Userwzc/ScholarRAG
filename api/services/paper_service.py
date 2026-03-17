import os
from typing import Any, Optional

from api.config import API_UPLOAD_DIR
from api.schemas import (
    ChunkItem,
    ChunkListResponse,
    PaperDetail,
    PaperItem,
    PaperUploadResponse,
)

def _get_vector_store():
    from src.rag.vector_store import vector_store
    return vector_store

def upload_paper(file_path: str) -> PaperUploadResponse:
    from src.core.ingestion import process_paper
    
    # Process paper using the unified ingestion logic
    multimodal_inputs, metadata_list, parsed_data = process_paper(file_path, save_markdown=False)

    pdf_name = parsed_data.get("pdf_name", "")
    paper_title = parsed_data.get("title", "Unknown Title")
    authors_str = ""

    if metadata_list:
        authors_str = metadata_list[0].get("authors", "")
        paper_title = metadata_list[0].get("title", paper_title)

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
    
    # Fetch just 1 chunk to get the metadata
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
    
    # Keeping array slicing for exact pagination behavior as original implementation
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
