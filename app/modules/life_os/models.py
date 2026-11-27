"""Owner-scoped originals and immutable successful analysis snapshots."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class Message(Base):
    __tablename__ = 'life_os_messages'
    __table_args__ = (UniqueConstraint('user_id','request_id',name='uq_life_os_message_request'), UniqueConstraint('id','user_id',name='uq_life_os_message_owner'))
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), index=True)
    request_id: Mapped[UUID] = mapped_column()
    content: Mapped[str] = mapped_column(Text)
    input_note_ids: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Analysis(Base):
    __tablename__ = 'life_os_analyses'
    __table_args__ = (UniqueConstraint('user_id','request_id',name='uq_life_os_analysis_request'), ForeignKeyConstraint(['message_id','user_id'],['life_os_messages.id','life_os_messages.user_id']))
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), index=True)
    message_id: Mapped[UUID] = mapped_column(index=True)
    request_id: Mapped[UUID] = mapped_column()
    status: Mapped[str] = mapped_column(String(20))
    error_code: Mapped[str | None] = mapped_column(String(50))
    result: Mapped[dict | None] = mapped_column(JSON)
    source_ids: Mapped[list] = mapped_column(JSON)
    prompt_version: Mapped[str] = mapped_column(String(30), default='life-core-v1')
    model_id: Mapped[str | None] = mapped_column(String(160))
    config_version: Mapped[int | None] = mapped_column()
    usage: Mapped[dict | None] = mapped_column(JSON)
    note_scope: Mapped[list | None] = mapped_column(JSON)
    experience_status: Mapped[str | None] = mapped_column(String(20))
    experience_error: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
