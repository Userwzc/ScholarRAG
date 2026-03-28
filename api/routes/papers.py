# pyright: reportMissingImports=false

import logging
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse
from sqlalchemy.exc import SQLAlchemyError

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
    PaperVersionItem,
    PaperVersionListResponse,
    TOCResponse,
)
from api.services import async_upload_service, paper_registry_service, paper_service
from src.utils.exceptions import (
    AppError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
    app_error_to_dict,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _as_http_exception(error: AppError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=app_error_to_dict(error))


@router.post("/uploads", response_model=IngestionJobCreateResponse, status_code=202)
async def async_upload_paper(file: UploadFile = File(...)):
    if file.filename is None or not file.filename.lower().endswith(".pdf"):
        raise _as_http_exception(ValidationError("Only PDF files are supported"))

    try:
        content = await file.read()
        async with get_db_session() as session:
            result = await async_upload_service.create_async_upload_job(
                session=session,
                file_content=content,
                filename=file.filename,
            )

        async_upload_service.start_background_ingestion(result.job_id)

        return result
    except (OSError, RuntimeError, ValueError, TypeError, SQLAlchemyError) as exc:
        logger.exception("Failed to start async upload: %s", exc)
        raise _as_http_exception(
            ExternalServiceError("Failed to start upload processing", log_message=str(exc))
        )


@router.get("/uploads", response_model=IngestionJobListResponse)
async def list_jobs(limit: int = Query(20, ge=1, le=100)):
    async with get_db_session() as session:
        return await async_upload_service.list_recent_jobs(session, limit)


@router.get("/uploads/{job_id}", response_model=IngestionJobResponse)
async def get_job_status(job_id: str):
    async with get_db_session() as session:
        job = await async_upload_service.get_job_status(session, job_id)
        if job is None:
            raise _as_http_exception(NotFoundError("Job not found"))
        return job


@router.post("/uploads/{job_id}/retry", response_model=IngestionJobRetryResponse)
async def retry_job(job_id: str):
    async with get_db_session() as session:
        job = await async_upload_service.get_job_status(session, job_id)
        if job is None:
            raise _as_http_exception(NotFoundError("Job not found"))

        if job.status != "failed":
            raise HTTPException(status_code=409, detail=app_error_to_dict(ValidationError("Retry is only allowed for failed jobs")))

        result = await async_upload_service.retry_failed_job(session, job_id)
        if result is None:
            raise _as_http_exception(ExternalServiceError("Failed to retry job"))

    async_upload_service.start_background_ingestion(job_id)
    return result


@router.post(
    "/{pdf_name}/reindex", response_model=IngestionJobCreateResponse, status_code=202
)
async def reindex_paper(pdf_name: str):
    try:
        async with get_db_session() as session:
            result = await async_upload_service.create_reindex_job(session, pdf_name)
            if result is None:
                raise _as_http_exception(
                    NotFoundError("Paper not found or source PDF unavailable")
                )

        async_upload_service.start_background_ingestion(result.job_id)
        return result
    except (OSError, RuntimeError, ValueError, TypeError, SQLAlchemyError) as exc:
        logger.exception("Failed to start reindex job: %s", exc)
        raise _as_http_exception(
            ExternalServiceError("Failed to start reindex processing", log_message=str(exc))
        )


@router.get("/{pdf_name}/versions", response_model=PaperVersionListResponse)
async def get_paper_versions(pdf_name: str):
    async with get_db_session() as session:
        paper = await paper_registry_service.get_paper_by_pdf_name(session, pdf_name)
        if paper is None:
            raise _as_http_exception(NotFoundError("Paper not found"))

        versions = await paper_registry_service.list_versions(session, paper.id)

    return PaperVersionListResponse(
        pdf_name=pdf_name,
        versions=[
            PaperVersionItem(
                id=version.id,
                version_number=version.version_number,
                is_current=version.is_current,
                source_hash=version.source_hash,
                ingestion_schema_version=version.ingestion_schema_version,
                created_at=version.created_at,
            )
            for version in versions
        ],
    )


@router.get("", response_model=PaperListResponse)
async def list_papers(version: Optional[int] = Query(None, ge=1)):
    try:
        papers = paper_service.list_papers(version=version)
        return PaperListResponse(papers=papers)
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        logger.exception("Failed to list papers: %s", exc)
        raise _as_http_exception(
            ExternalServiceError("Failed to list papers", log_message=str(exc))
        )


@router.get("/{pdf_name}", response_model=PaperDetail)
async def get_paper(pdf_name: str, version: Optional[int] = Query(None, ge=1)):
    paper = paper_service.get_paper_detail(pdf_name, version=version)
    if paper is None:
        raise _as_http_exception(NotFoundError("Paper not found"))
    return paper


@router.delete("/{pdf_name}", response_model=DeleteResponse)
async def delete_paper(pdf_name: str):
    try:
        success = paper_service.delete_paper(pdf_name)
        if not success:
            raise _as_http_exception(NotFoundError("Paper not found"))
        return DeleteResponse(message=f"Paper {pdf_name} deleted successfully")
    except HTTPException:
        raise
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        logger.exception("Failed to delete paper: %s", exc)
        raise _as_http_exception(
            ExternalServiceError("Failed to delete paper", log_message=str(exc))
        )


@router.get("/{pdf_name}/chunks", response_model=ChunkListResponse)
async def get_paper_chunks(
    pdf_name: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    type: Optional[str] = Query(None, alias="type"),
    version: Optional[int] = Query(None, ge=1),
):
    try:
        return paper_service.get_paper_chunks(
            pdf_name,
            page,
            limit,
            type,
            version=version,
        )
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        logger.exception("Failed to get paper chunks: %s", exc)
        raise _as_http_exception(
            ExternalServiceError("Failed to get paper chunks", log_message=str(exc))
        )


@router.get("/{pdf_name}/pdf")
async def get_pdf_file(pdf_name: str):
    pdf_path = paper_service.get_pdf_path(pdf_name)
    if pdf_path is None:
        raise _as_http_exception(NotFoundError("PDF file not found"))
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"{pdf_name}.pdf",
    )


@router.get("/{pdf_name}/toc", response_model=TOCResponse)
async def get_paper_toc(pdf_name: str, version: Optional[int] = Query(None, ge=1)):
    toc = paper_service.get_paper_toc(pdf_name, version=version)
    if toc is None:
        raise _as_http_exception(NotFoundError("Paper not found"))
    return toc
