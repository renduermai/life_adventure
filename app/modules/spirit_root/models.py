"""Saved originals, canonical entries and source-level observations."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint,
    JSON, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProbeSource(Base):
    __tablename__ = 'spirit_root_sources'
    __table_args__ = (
        UniqueConstraint('user_id', 'digest', name='uq_spirit_root_source_digest'),
        UniqueConstraint('id', 'user_id', name='uq_spirit_root_source_owner'),
        CheckConstraint("state IN ('running','succeeded','failed')", name='ck_spirit_root_source_state'),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    digest: Mapped[str] = mapped_column(String(64))
    original: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(10))
    development: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    attempt_id: Mapped[UUID] = mapped_column()
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RootEntry(Base):
    __tablename__ = 'spirit_root_entries'
    __table_args__ = (
        UniqueConstraint('user_id', 'kind', 'label_key', name='uq_spirit_root_entry_label'),
        UniqueConstraint('id', 'user_id', name='uq_spirit_root_entry_owner'),
        CheckConstraint("kind IN ('talent','signal')", name='ck_spirit_root_entry_kind'),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    kind: Mapped[str] = mapped_column(String(8))
    label: Mapped[str] = mapped_column(String(80))
    label_key: Mapped[str] = mapped_column(String(256))


class Observation(Base):
    __tablename__ = 'spirit_root_observations'
    __table_args__ = (
        ForeignKeyConstraint(['source_id', 'user_id'], ['spirit_root_sources.id', 'spirit_root_sources.user_id'],
                             name='fk_spirit_root_observation_source'),
        ForeignKeyConstraint(['entry_id', 'user_id'], ['spirit_root_entries.id', 'spirit_root_entries.user_id'],
                             name='fk_spirit_root_observation_entry'),
        ForeignKeyConstraint(['suggested_id', 'user_id'], ['spirit_root_entries.id', 'spirit_root_entries.user_id'],
                             name='fk_spirit_root_observation_suggestion'),
        UniqueConstraint('source_id', 'entry_id', name='uq_spirit_root_entry_source'),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), index=True)
    source_id: Mapped[UUID] = mapped_column()
    entry_id: Mapped[UUID | None] = mapped_column(index=True)
    suggested_id: Mapped[UUID | None] = mapped_column()
    kind: Mapped[str] = mapped_column(String(8))
    label: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    strength: Mapped[str | None] = mapped_column(String(12))
    reason: Mapped[str] = mapped_column(Text)
    quote: Mapped[str] = mapped_column(Text)
    linked_talents: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
