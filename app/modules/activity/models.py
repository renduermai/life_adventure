"""Durable focus sessions and user-owned activity records."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, JSON, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class FocusSession(Base):
    __tablename__ = 'focus_sessions'
    __table_args__ = (
        UniqueConstraint('id', 'user_id', name='uq_focus_id_user'),
        ForeignKeyConstraint(['task_id','user_id'], ['tasks.id','tasks.user_id'], name='fk_focus_task_owner'),
        CheckConstraint("status IN ('running','paused','finished')", name='ck_focus_status'),
        CheckConstraint("mode IN ('elapsed','countdown')", name='ck_focus_mode'),
        CheckConstraint('accumulated_seconds >= 0 AND (target_seconds IS NULL OR target_seconds > 0)', name='ck_focus_seconds'),
        Index('uq_focus_active_user', 'user_id', unique=True, postgresql_where=text("status IN ('running','paused')")),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), index=True)
    task_id: Mapped[UUID | None] = mapped_column()
    status: Mapped[str] = mapped_column(String(16))
    mode: Mapped[str] = mapped_column(String(16))
    target_seconds: Mapped[int | None] = mapped_column(Integer)
    accumulated_seconds: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ActivityLog(Base):
    __tablename__ = 'activity_logs'
    __table_args__ = (
        ForeignKeyConstraint(['task_id','user_id'], ['tasks.id','tasks.user_id'], name='fk_activity_task_owner'),
        ForeignKeyConstraint(['session_id','user_id'], ['focus_sessions.id','focus_sessions.user_id'], name='fk_activity_session_owner'),
        CheckConstraint('duration_seconds >= 0', name='ck_activity_duration'),
        UniqueConstraint('session_id', name='uq_activity_session'),
        UniqueConstraint('id', 'user_id', name='uq_activity_id_user'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), index=True)
    task_id: Mapped[UUID | None] = mapped_column()
    session_id: Mapped[UUID | None] = mapped_column()
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(60), default='')
    note: Mapped[str] = mapped_column(Text, default='')
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class FocusSegment(Base):
    __tablename__ = 'focus_segments'
    __table_args__ = (ForeignKeyConstraint(['session_id','user_id'], ['focus_sessions.id','focus_sessions.user_id'], name='fk_segment_session_owner'),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), index=True)
    session_id: Mapped[UUID] = mapped_column(index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActivityEvent(Base):
    __tablename__ = 'activity_events'
    __table_args__ = (ForeignKeyConstraint(['activity_id','user_id'], ['activity_logs.id','activity_logs.user_id'], name='fk_activity_event_owner'),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), index=True)
    activity_id: Mapped[UUID] = mapped_column(index=True)
    action: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
