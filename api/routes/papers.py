import logging
from typing import Optional
from fastapi import APIRouter, File, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse

from api.database import get_db_session
from api.schemas import (
    ChunkListResponse,
    DeleteResponse,
    IngestionJobCreateResponse,
    IngestionJobListResponse,
    IngestionJobResponse,
    IngestionJobRetryResponse,
    PaperDetail,
    PaperListResponse,
    PaperUploadResponse,
    TOCResponse,
)
from api.services import async_upload_service, paper_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/upload", response_model=PaperUploadResponse)
async def upload_paper(file: UploadFile = File(...)):
    if file.filename is None or not file.filename.lower().endswith(".pdf"):
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
        logger.exception("Failed to upload paper: %s", e)
        raise HTTPException(status_code=500, detail="Failed to upload paper")


@router.post("/uploads", response_model=IngestionJobCreateResponse, status_code=202)
async def async_upload_paper(file: UploadFile = File(...)):
    if file.filename is None or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        content = await file.read()
        async with get_db_session() as session:
            result = await async_upload_service.create_async_upload_job(
                session=session,
                file_content=content,
                filename=file.filename,
            )

        return result
    except Exception as e:
        logger.exception("Failed to start async upload: %s", e)
        raise HTTPException(status_code=500, detail="Failed to start upload processing")


@router.get("/uploads", response_model=IngestionJobListResponse)
async def list_jobs(limit: int = Query(20, ge=1, le=100)):
    async with get_db_session() as session:
        return await async_upload_service.list_recent_jobs(session, limit)


@router.get("/uploads/{job_id}", response_model=IngestionJobResponse)
async def get_job_status(job_id: str):
    async with get_db_session() as session:
        job = await async_upload_service.get_job_status(session, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job


@router.post("/uploads/{job_id}/retry", response_model=IngestionJobRetryResponse)
async def retry_job(job_id: str):
    async with get_db_session() as session:
        job = await async_upload_service.get_job_status(session, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.status != "failed":
            raise HTTPException(
                status_code=409,
                detail="Retry is only allowed for failed jobs",
            )

        result = await async_upload_service.retry_failed_job(session, job_id)
        if result is None:
            raise HTTPException(status_code=500, detail="Failed to retry job")
        return result


@router.get("", response_model=PaperListResponse)
async def list_papers():
    try:
        papers = paper_service.list_papers()
        return PaperListResponse(papers=papers)
    except Exception as e:
        logger.exception("Failed to list papers: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list papers")


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
        logger.exception("Failed to delete paper: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete paper")


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
        logger.exception("Failed to get paper chunks: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get paper chunks")


@router.get("/{pdf_name}/pdf")
async def get_pdf_file(pdf_name: str):
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
    toc = paper_service.get_paper_toc(pdf_name)
    if toc is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return toc
