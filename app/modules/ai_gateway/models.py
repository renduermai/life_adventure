from datetime import date, datetime
from uuid import UUID, uuid4
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class AIConfig(Base):
    __tablename__ = 'ai_configs'
    __table_args__ = (
        UniqueConstraint('id', 'user_id', name='uq_ai_config_owner'),
        UniqueConstraint('user_id', 'create_request_id', name='uq_ai_config_request'),
        CheckConstraint('config_version >= 1', name='ck_ai_config_version'),
        CheckConstraint("protocol = 'openai_compatible'", name='ck_ai_protocol'),
        CheckConstraint('NOT is_default OR (enabled AND deleted_at IS NULL)', name='ck_ai_default_enabled'),
        Index('uq_ai_default', 'user_id', unique=True, postgresql_where=text('is_default')),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), index=True)
    create_request_id: Mapped[UUID] = mapped_column()
    create_fingerprint: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(80))
    base_url: Mapped[str] = mapped_column(String(500))
    model_id: Mapped[str] = mapped_column(String(160))
    protocol: Mapped[str] = mapped_column(String(32), default='openai_compatible')
    encrypted_key: Mapped[str | None] = mapped_column(Text)
    key_version: Mapped[str] = mapped_column(String(16))
    key_mask: Mapped[str] = mapped_column(String(16), default='已设置')
    expires_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(String(2000), default='')
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    last_test_version: Mapped[int | None] = mapped_column(Integer)
    last_test_result: Mapped[str | None] = mapped_column(String(40))
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AIModuleBinding(Base):
    __tablename__ = 'ai_module_bindings'
    __table_args__ = (ForeignKeyConstraint(['config_id','user_id'], ['ai_configs.id','ai_configs.user_id'], name='fk_ai_binding_owner'),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), primary_key=True)
    module_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    config_id: Mapped[UUID] = mapped_column()


class AICallLog(Base):
    __tablename__ = 'ai_call_logs'
    __table_args__ = (
        ForeignKeyConstraint(['config_id','user_id'], ['ai_configs.id','ai_configs.user_id'], name='fk_ai_call_owner'),
        UniqueConstraint('user_id', 'purpose', 'request_id', name='uq_ai_call_request'),
        CheckConstraint("status IN ('running','succeeded','failed','unknown')", name='ck_ai_call_status'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), index=True)
    config_id: Mapped[UUID] = mapped_column()
    config_version: Mapped[int] = mapped_column(Integer)
    model_id: Mapped[str] = mapped_column(String(160))
    purpose: Mapped[str] = mapped_column(String(40))
    request_id: Mapped[UUID] = mapped_column()
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    error_code: Mapped[str | None] = mapped_column(String(40))
    usage: Mapped[dict | None] = mapped_column(JSON)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
