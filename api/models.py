"""
SQLAlchemy ORM 模型定义。

定义 Conversation 和 Message 两个模型，用于持久化对话历史。
"""

from typing import Optional

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base


class Conversation(Base):
    """
    对话模型。

    存储对话的元数据，与消息是一对多关系。
    """

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)

    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    """
    消息模型。

    存储单条消息的内容和元数据，与对话是多对一关系。
    """

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    steps: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sources: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)

    conversation: Mapped["Conversation"] = relationship(
        "Conversation",
        back_populates="messages",
    )
