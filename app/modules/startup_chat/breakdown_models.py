from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class BreakdownPlan(Base):
    __tablename__ = 'breakdown_plans'
    __table_args__ = (
        UniqueConstraint('id', 'user_id', name='uq_breakdown_owner'),
        UniqueConstraint('user_id', 'request_id', name='uq_breakdown_request'),
        ForeignKeyConstraint(['quest_id', 'user_id'], ['main_quests.id', 'main_quests.user_id'], name='fk_breakdown_quest'),
        ForeignKeyConstraint(['task_id', 'user_id'], ['tasks.id', 'tasks.user_id'], name='fk_breakdown_task'),
        ForeignKeyConstraint(['snapshot_id', 'user_id'], ['startup_state_snapshots.id', 'startup_state_snapshots.user_id'], name='fk_breakdown_state'),
        ForeignKeyConstraint(['previous_id', 'user_id'], ['breakdown_plans.id', 'breakdown_plans.user_id'], name='fk_breakdown_previous'),
        CheckConstraint('(quest_id IS NULL) != (task_id IS NULL)', name='ck_breakdown_target'),
        CheckConstraint("status IN ('generating','draft','confirmed','failed','superseded')", name='ck_breakdown_status'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), index=True)
    quest_id: Mapped[UUID | None] = mapped_column()
    task_id: Mapped[UUID | None] = mapped_column()
    snapshot_id: Mapped[UUID | None] = mapped_column()
    previous_id: Mapped[UUID | None] = mapped_column()
    request_id: Mapped[UUID] = mapped_column()
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    context_fingerprint: Mapped[str] = mapped_column(String(64))
    context: Mapped[dict] = mapped_column(JSON)
    feedback: Mapped[str] = mapped_column(String(2000), default='')
    status: Mapped[str] = mapped_column(String(16), default='generating')
    revision: Mapped[int] = mapped_column(Integer, default=1)
    advice: Mapped[dict | None] = mapped_column(JSON)
    model_info: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(50))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmation_fingerprint: Mapped[str | None] = mapped_column(String(64))
    save_mode: Mapped[str | None] = mapped_column(String(20))
    mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    execution: Mapped[dict] = mapped_column(JSON, default=dict)
    checklist: Mapped[dict] = mapped_column(JSON, default=dict)
    checklist_version: Mapped[int] = mapped_column(Integer, default=0)
    checklist_events: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
