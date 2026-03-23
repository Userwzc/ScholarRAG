"""
对话历史服务层。

提供对话和消息的 CRUD 操作，用于持久化用户的对话历史。
"""

import json
import time
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models import Conversation, Message
from api.schemas import (
    AgentStepSchema,
    ConversationDetail,
    ConversationListItem,
    MessageCreate,
    MessageResponse,
    SourceSchema,
)


async def create_conversation(
    session: AsyncSession,
    conversation_id: str,
    title: str = "New Chat",
) -> Conversation:
    """
    创建新对话。

    Args:
        session: 数据库会话
        conversation_id: 对话 ID（前端生成）
        title: 对话标题

    Returns:
        创建的对话对象
    """
    now = int(time.time() * 1000)
    conversation = Conversation(
        id=conversation_id,
        title=title,
        created_at=now,
        updated_at=now,
    )
    session.add(conversation)
    await session.flush()
    return conversation


async def get_conversation(
    session: AsyncSession,
    conversation_id: str,
) -> Optional[Conversation]:
    """
    获取对话详情。

    Args:
        session: 数据库会话
        conversation_id: 对话 ID

    Returns:
        对话对象，不存在则返回 None
    """
    result = await session.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
    )
    return result.scalar_one_or_none()


async def get_all_conversations(session: AsyncSession) -> list[ConversationListItem]:
    """
    获取所有对话列表。

    按更新时间倒序排列，包含消息数量。

    Args:
        session: 数据库会话

    Returns:
        对话列表
    """
    subquery = (
        select(
            Message.conversation_id,
            func.count(Message.id).label("message_count"),
        )
        .group_by(Message.conversation_id)
        .subquery()
    )

    result = await session.execute(
        select(
            Conversation.id,
            Conversation.title,
            Conversation.created_at,
            Conversation.updated_at,
            func.coalesce(subquery.c.message_count, 0).label("message_count"),
        )
        .outerjoin(subquery, Conversation.id == subquery.c.conversation_id)
        .order_by(Conversation.updated_at.desc())
    )

    conversations = []
    for row in result:
        conversations.append(
            ConversationListItem(
                id=row.id,
                title=row.title,
                created_at=row.created_at,
                updated_at=row.updated_at,
                message_count=row.message_count,
            )
        )
    return conversations


async def delete_conversation(
    session: AsyncSession,
    conversation_id: str,
) -> bool:
    """
    删除对话及其所有消息。

    Args:
        session: 数据库会话
        conversation_id: 对话 ID

    Returns:
        是否成功删除
    """
    result = await session.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        return False

    await session.delete(conversation)
    return True


async def add_message(
    session: AsyncSession,
    conversation_id: str,
    message: MessageCreate,
) -> Optional[Message]:
    """
    向对话添加消息。

    同时更新对话的 updated_at 时间戳。

    Args:
        session: 数据库会话
        conversation_id: 对话 ID
        message: 消息数据

    Returns:
        创建的消息对象，对话不存在则返回 None
    """
    result = await session.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        return None

    steps_json = (
        json.dumps([s.model_dump() for s in message.steps]) if message.steps else None
    )
    sources_json = (
        json.dumps([s.model_dump() for s in message.sources])
        if message.sources
        else None
    )

    db_message = Message(
        id=message.id,
        conversation_id=conversation_id,
        role=message.role,
        content=message.content,
        steps=steps_json,
        sources=sources_json,
        created_at=message.created_at,
    )
    session.add(db_message)

    conversation.updated_at = int(time.time() * 1000)

    await session.flush()
    return db_message


def message_to_response(message: Message) -> MessageResponse:
    """
    将数据库消息对象转换为响应模型。

    Args:
        message: 数据库消息对象

    Returns:
        消息响应模型
    """
    steps = None
    if message.steps:
        try:
            steps_data = json.loads(message.steps)
            steps = [AgentStepSchema(**s) for s in steps_data]
        except (json.JSONDecodeError, TypeError):
            pass

    sources = None
    if message.sources:
        try:
            sources_data = json.loads(message.sources)
            sources = [SourceSchema(**s) for s in sources_data]
        except (json.JSONDecodeError, TypeError):
            pass

    return MessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        steps=steps,
        sources=sources,
        created_at=message.created_at,
    )


def conversation_to_detail(conversation: Conversation) -> ConversationDetail:
    """
    将数据库对话对象转换为详情响应模型。

    Args:
        conversation: 数据库对话对象

    Returns:
        对话详情响应模型
    """
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[message_to_response(m) for m in conversation.messages],
    )
