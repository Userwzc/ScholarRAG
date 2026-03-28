# pyright: reportMissingImports=false

"""
查询路由。

处理用户查询请求，支持流式响应和多轮对话上下文。
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.database import get_db_session
from api.schemas import MessageCreate, QueryRequest
from api.services import conversation_service, query_service
from src.utils.exceptions import (
    AppError,
    ExternalServiceError,
    ValidationError,
    app_error_to_dict,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _as_http_exception(error: AppError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=app_error_to_dict(error))


@router.post("")
async def query(request: QueryRequest):
    """
    执行查询并流式返回结果。

    如果提供 conversation_id，会保存用户消息到数据库，
    并传递历史消息给 Agent 以支持多轮对话。
    """
    if not request.question.strip():
        raise _as_http_exception(ValidationError("Question cannot be empty"))

    # 如果提供了 conversation_id，保存用户消息
    if request.conversation_id:
        async with get_db_session() as session:
            await conversation_service.add_message(
                session,
                request.conversation_id,
                MessageCreate(
                    id=f"msg_user_{uuid.uuid4().hex[:12]}",
                    role="user",
                    content=request.question,
                    created_at=int(uuid.uuid1().time // 1000),
                ),
            )

    try:
        return StreamingResponse(
            query_service.stream_query(
                question=request.question,
                history=request.history,
            ),
            media_type="text/event-stream",
        )
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        logger.exception("Query processing failed: %s", exc)
        raise _as_http_exception(
            ExternalServiceError("Query processing failed", log_message=str(exc))
        )
