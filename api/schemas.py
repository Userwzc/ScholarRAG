from typing import Any, Optional
from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    status: str
    message: Optional[str] = None


class PaperUploadResponse(BaseModel):
    pdf_name: str
    title: str
    authors: str
    chunk_count: int
    message: str


class PaperItem(BaseModel):
    pdf_name: str
    title: str
    authors: str
    chunk_count: int
    created_at: Optional[str] = None


class PaperListResponse(BaseModel):
    papers: list[PaperItem]


class PaperDetail(BaseModel):
    pdf_name: str
    title: str
    authors: str
    chunk_count: int
    metadata: dict[str, Any]


class ChunkItem(BaseModel):
    id: str
    content: str
    chunk_type: str
    page_idx: Optional[int] = None
    heading: Optional[str] = None
    score: Optional[float] = None
    image: Optional[str] = None


class ChunkListResponse(BaseModel):
    chunks: list[ChunkItem]
    total: int
    page: int
    limit: int


class DeleteResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str


class SSEToken(BaseModel):
    text: str


class SSEToolCall(BaseModel):
    tool: str
    kind: str
    args: dict[str, Any]
    step: int


class SSEToolResult(BaseModel):
    kind: str
    count: int
    pages: list[str]


class SSEStatus(BaseModel):
    phase: str
    step: int
    text: str
