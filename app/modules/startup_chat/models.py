from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Conversation(Base):
    __tablename__ = 'startup_conversations'
    __table_args__ = (UniqueConstraint('id', 'user_id', name='uq_chat_owner'),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(String(60))
    selected_target_key: Mapped[str | None] = mapped_column(String(48), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatTurn(Base):
    __tablename__ = 'startup_chat_turns'
    __table_args__ = (
        UniqueConstraint('id', 'user_id', name='uq_chat_turn_owner'),
        UniqueConstraint('user_id', 'request_id', name='uq_chat_request'),
        UniqueConstraint('conversation_id', 'sequence', name='uq_chat_sequence'),
        ForeignKeyConstraint(['conversation_id', 'user_id'], ['startup_conversations.id', 'startup_conversations.user_id'], name='fk_chat_conversation_owner'),
        CheckConstraint("status IN ('pending','succeeded','failed')", name='ck_chat_status'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), index=True)
    conversation_id: Mapped[UUID] = mapped_column()
    request_id: Mapped[UUID] = mapped_column()
    fingerprint: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int] = mapped_column(Integer)
    base_generation: Mapped[int] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(String(2000))
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default='pending')
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
