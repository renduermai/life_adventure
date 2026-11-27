from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("manual_focus_status IN ('recommended','normal','not_recommended','deferred','routine_practice')", name='ck_tasks_manual_focus'),
        CheckConstraint('manual_focus_version >= 1', name='ck_tasks_manual_focus_version'),
        UniqueConstraint("id", "user_id", name="uq_task_id_user"),
        ForeignKeyConstraint(["main_quest_id", "user_id"], ["main_quests.id", "main_quests.user_id"], name="fk_task_quest_owner"),
        ForeignKeyConstraint(["milestone_id", "main_quest_id", "user_id"], ["milestones.id", "milestones.main_quest_id", "milestones.user_id"], name="fk_task_milestone_owner"),
        ForeignKeyConstraint(["parent_task_id", "user_id"], ["tasks.id", "tasks.user_id"], name="fk_task_parent_owner"),
        ForeignKeyConstraint(["recurrence_from_id", "user_id"], ["tasks.id", "tasks.user_id"], name="fk_task_recurrence_owner"),
        CheckConstraint("status IN ('todo','in_progress','completed')", name="ck_task_status"),
        CheckConstraint("priority IN ('low','normal','high')", name="ck_task_priority"),
        CheckConstraint("repeat_rule IN ('none','daily','weekly','monthly')", name="ck_task_repeat"),
        CheckConstraint("milestone_id IS NULL OR main_quest_id IS NOT NULL", name="ck_task_milestone_quest"),
        CheckConstraint("parent_task_id IS NULL OR parent_task_id != id", name="ck_task_not_self"),
        CheckConstraint("parent_task_id IS NULL OR repeat_rule = 'none'", name="ck_task_child_repeat"),
        CheckConstraint("completion_round >= 0 AND version >= 1", name="ck_task_counters"),
        CheckConstraint("(status = 'completed') = (completed_at IS NOT NULL)", name="ck_task_completed_at"),
    )
    manual_focus_status: Mapped[str] = mapped_column(String(24), nullable=False, default='normal', server_default='normal')
    manual_focus_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text('1'))
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    main_quest_id: Mapped[UUID | None] = mapped_column(index=True)
    milestone_id: Mapped[UUID | None] = mapped_column(index=True)
    parent_task_id: Mapped[UUID | None] = mapped_column(index=True)
    recurrence_from_id: Mapped[UUID | None] = mapped_column(unique=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(60), default="")
    priority: Mapped[str] = mapped_column(String(12), default="normal")
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="todo")
    repeat_rule: Mapped[str] = mapped_column(String(12), default="none")
    completion_round: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TaskEvent(Base):
    __tablename__ = "task_events"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_task_event_id_user"),
        ForeignKeyConstraint(["task_id", "user_id"], ["tasks.id", "tasks.user_id"], name="fk_task_event_owner"),
        Index("uq_task_completion_event", "task_id", "completion_round", "kind", unique=True,
              postgresql_where=text("kind IN ('completed','reopened')")),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    task_id: Mapped[UUID] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(String(24))
    completion_round: Mapped[int] = mapped_column(Integer)
    reversal_of: Mapped[UUID | None] = mapped_column(ForeignKey("task_events.id"), unique=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaskCommand(Base):
    __tablename__ = "task_commands"
    __table_args__ = (UniqueConstraint("user_id", "request_id", name="uq_task_command_request"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    request_id: Mapped[UUID] = mapped_column()
    fingerprint: Mapped[str] = mapped_column(String(64))
    result_task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
