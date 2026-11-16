from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class StartupItem(Base):
    __tablename__ = 'startup_items'
    __table_args__ = (
        UniqueConstraint('user_id', 'create_request_id', name='uq_startup_item_request'),
        CheckConstraint('importance BETWEEN 0 AND 100', name='ck_startup_item_importance'),
        CheckConstraint('urgency BETWEEN 0 AND 100', name='ck_startup_item_urgency'),
        CheckConstraint('version >= 1', name='ck_startup_item_version'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), index=True)
    description: Mapped[str] = mapped_column(String(2000))
    importance: Mapped[int] = mapped_column(Integer)
    urgency: Mapped[int] = mapped_column(Integer)
    progress: Mapped[str] = mapped_column(String(2000), default='')
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text('1'))
    create_request_id: Mapped[UUID] = mapped_column()
    create_fingerprint: Mapped[str] = mapped_column(String(64))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
