"""Stable assets and immutable cloud object revisions, including failed uploads."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class MemoryAsset(Base):
    __tablename__ = 'memory_assets'
    __table_args__ = (
        UniqueConstraint('id', 'user_id', name='uq_memory_asset_owner'),
        UniqueConstraint('user_id', 'create_request_id', name='uq_memory_asset_request'),
        CheckConstraint('version >= 1', name='ck_memory_asset_version'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    create_request_id: Mapped[UUID] = mapped_column()
    create_fingerprint: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text('1'))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MemoryObject(Base):
    __tablename__ = 'memory_asset_objects'
    __table_args__ = (
        ForeignKeyConstraint(['asset_id', 'user_id'], ['memory_assets.id', 'memory_assets.user_id'], name='fk_memory_object_owner'),
        UniqueConstraint('user_id', 'request_id', name='uq_memory_object_request'),
        UniqueConstraint('bucket', 'object_path', name='uq_memory_object_key'),
        CheckConstraint("state IN ('pending','active','retired','deleted')", name='ck_memory_object_state'),
        CheckConstraint("byte_size BETWEEN 1 AND 5242880 AND width > 0 AND height > 0 AND width * height <= 12000000", name='ck_memory_object_size'),
        CheckConstraint("content_type = 'image/webp'", name='ck_memory_object_type'),
        Index('uq_memory_object_active', 'asset_id', unique=True, postgresql_where=text("state = 'active'")),
        Index('ix_memory_object_cleanup', 'state', 'delete_after'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column()
    user_id: Mapped[UUID] = mapped_column()
    request_id: Mapped[UUID] = mapped_column()
    fingerprint: Mapped[str] = mapped_column(String(64))
    bucket: Mapped[str] = mapped_column(String(63))
    object_path: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(32), default='image/webp')
    state: Mapped[str] = mapped_column(String(12), default='pending')
    error_code: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    delete_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
