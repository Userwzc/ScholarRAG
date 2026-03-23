from typing import Any, Optional

from pydantic import BaseModel


class MessageHistory(BaseModel):
    role: str
    content: str


class QueryRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    history: list[MessageHistory] = []


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


class TOCItem(BaseModel):
    """Table of contents item for PDF reader."""

    id: str
    level: int
    text: str
    page_idx: int
    chunk_type: str  # "section" | "image" | "table"


class TOCResponse(BaseModel):
    """Table of contents response for a paper."""

    items: list[TOCItem]
    total_pages: int


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


class AgentStepSchema(BaseModel):
    type: str
    tool: Optional[str] = None
    text: Optional[str] = None
    count: Optional[int] = None
    pages: Optional[list[str]] = None


class SourceSchema(BaseModel):
    pdf_name: str
    page: int
    type: str


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    steps: Optional[list[AgentStepSchema]] = None
    sources: Optional[list[SourceSchema]] = None
    created_at: int


class ConversationCreate(BaseModel):
    id: str
    title: str = "New Chat"


class ConversationUpdate(BaseModel):
    title: str


class ConversationListItem(BaseModel):
    id: str
    title: str
    created_at: int
    updated_at: int
    message_count: int


class ConversationListResponse(BaseModel):
    conversations: list[ConversationListItem]


class ConversationDetail(BaseModel):
    id: str
    title: str
    created_at: int
    updated_at: int
    messages: list[MessageResponse]


class MessageCreate(BaseModel):
    id: str
    role: str
    content: str
    steps: Optional[list[AgentStepSchema]] = None
    sources: Optional[list[SourceSchema]] = None
    created_at: int
