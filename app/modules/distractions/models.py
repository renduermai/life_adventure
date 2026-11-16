from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, func, text
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


class ClassificationRun(Base):
    __tablename__ = 'distraction_classification_runs'
    __table_args__ = (UniqueConstraint('user_id', 'request_id', name='uq_distraction_run_request'),
                     UniqueConstraint('id', 'user_id', name='uq_distraction_run_owner'))
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), index=True)
    request_id: Mapped[UUID] = mapped_column()
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    error_code: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DistractionTopic(Base):
    __tablename__ = 'distraction_topics'
    __table_args__ = (
        ForeignKeyConstraint(['run_id','user_id'], ['distraction_classification_runs.id','distraction_classification_runs.user_id']),
        UniqueConstraint('id','run_id','user_id', name='uq_distraction_topic_owner'))
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column()
    user_id: Mapped[UUID] = mapped_column()
    category: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(String(300))


class DistractionMembership(Base):
    __tablename__ = 'distraction_memberships'
    __table_args__ = (
        ForeignKeyConstraint(['run_id','user_id'], ['distraction_classification_runs.id','distraction_classification_runs.user_id']),
        ForeignKeyConstraint(['note_id','user_id'], ['distraction_notes.id','distraction_notes.user_id']),
        ForeignKeyConstraint(['topic_id','run_id','user_id'], ['distraction_topics.id','distraction_topics.run_id','distraction_topics.user_id']))
    run_id: Mapped[UUID] = mapped_column(primary_key=True)
    note_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column()
    topic_id: Mapped[UUID | None] = mapped_column()
