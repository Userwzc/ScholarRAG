from typing import Optional
from fastapi import APIRouter, File, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse

from api.schemas import (
    ChunkListResponse,
    DeleteResponse,
    PaperDetail,
    PaperListResponse,
    PaperUploadResponse,
    TOCResponse,
)
from api.services import paper_service

router = APIRouter()


@router.post("/upload", response_model=PaperUploadResponse)
async def upload_paper(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        content = await file.read()
        file_path = paper_service.save_uploaded_file(content, file.filename)

        try:
            result = paper_service.upload_paper(file_path)
        finally:
            paper_service.cleanup_uploaded_file(file_path)

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=PaperListResponse)
async def list_papers():
    try:
        papers = paper_service.list_papers()
        return PaperListResponse(papers=papers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{pdf_name}", response_model=PaperDetail)
async def get_paper(pdf_name: str):
    paper = paper_service.get_paper_detail(pdf_name)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@router.delete("/{pdf_name}", response_model=DeleteResponse)
async def delete_paper(pdf_name: str):
    try:
        success = paper_service.delete_paper(pdf_name)
        if not success:
            raise HTTPException(status_code=404, detail="Paper not found")
        return DeleteResponse(message=f"Paper {pdf_name} deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{pdf_name}/chunks", response_model=ChunkListResponse)
async def get_paper_chunks(
    pdf_name: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    type: Optional[str] = Query(None, alias="type"),
):
    try:
        return paper_service.get_paper_chunks(pdf_name, page, limit, type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{pdf_name}/pdf")
async def get_pdf_file(pdf_name: str):
    """Return the original PDF file for the reader."""
    pdf_path = paper_service.get_pdf_path(pdf_name)
    if pdf_path is None:
        raise HTTPException(status_code=404, detail="PDF file not found")
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"{pdf_name}.pdf",
    )


@router.get("/{pdf_name}/toc", response_model=TOCResponse)
async def get_paper_toc(pdf_name: str):
    """Return table of contents for the PDF reader."""
    toc = paper_service.get_paper_toc(pdf_name)
    if toc is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return toc
