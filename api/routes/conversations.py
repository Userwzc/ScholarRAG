"""
对话历史路由。

提供对话的 CRUD 接口，支持前端同步对话历史。
"""

import time

from fastapi import APIRouter, HTTPException

from api.database import get_db_session
from api.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationListResponse,
    ConversationUpdate,
    MessageCreate,
    MessageResponse,
)
from api.services import conversation_service

router = APIRouter()


@router.get("", response_model=ConversationListResponse)
async def list_conversations():
    """
    获取所有对话列表。

    按更新时间倒序返回，包含消息数量。
    """
    async with get_db_session() as session:
        conversations = await conversation_service.get_all_conversations(session)
        return ConversationListResponse(conversations=conversations)


@router.post("", status_code=201)
async def create_conversation(request: ConversationCreate):
    """
    创建新对话。

    对话 ID 由前端生成，确保与 localStorage 保持一致。
    """
    async with get_db_session() as session:
        existing = await conversation_service.get_conversation(session, request.id)
        if existing:
            return {"status": "ok", "message": "Conversation already exists"}

        await conversation_service.create_conversation(
            session,
            conversation_id=request.id,
            title=request.title,
        )
        return {"status": "ok", "id": request.id}


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str):
    """
    获取对话详情，包含所有消息。
    """
    async with get_db_session() as session:
        conversation = await conversation_service.get_conversation(
            session, conversation_id
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return conversation_service.conversation_to_detail(conversation)


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """
    删除对话及其所有消息。
    """
    async with get_db_session() as session:
        success = await conversation_service.delete_conversation(
            session, conversation_id
        )
        if not success:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return {"status": "ok", "message": "Conversation deleted"}


@router.patch("/{conversation_id}")
async def update_conversation(conversation_id: str, request: ConversationUpdate):
    """
    更新对话标题。
    """
    async with get_db_session() as session:
        conversation = await conversation_service.get_conversation(
            session, conversation_id
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        conversation.title = request.title
        conversation.updated_at = int(time.time() * 1000)

        return {"status": "ok", "message": "Conversation updated"}


@router.post(
    "/{conversation_id}/messages", response_model=MessageResponse, status_code=201
)
async def add_message(conversation_id: str, request: MessageCreate):
    """
    向对话添加消息。

    用于保存助手回复等后续消息。
    """
    async with get_db_session() as session:
        message = await conversation_service.add_message(
            session, conversation_id, request
        )
        if message is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return conversation_service.message_to_response(message)
