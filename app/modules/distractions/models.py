from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class DistractionNote(Base):
    __tablename__ = 'distraction_notes'
    __table_args__ = (
        UniqueConstraint('user_id', 'create_request_id', name='uq_distraction_note_request'),
        UniqueConstraint('id', 'user_id', name='uq_distraction_note_owner'),
        CheckConstraint('version >= 1', name='ck_distraction_note_version'),
        CheckConstraint('char_length(content) BETWEEN 1 AND 5000', name='ck_distraction_note_length'),
        Index('ix_distraction_notes_user_created', 'user_id', 'created_at', 'id'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    content: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text('1'))
    create_request_id: Mapped[UUID] = mapped_column()
    create_fingerprint: Mapped[str] = mapped_column(String(64))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
