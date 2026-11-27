"""Experience and virtual coin reward ledger."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class RewardSettings(Base):
    __tablename__ = 'reward_settings'
    __table_args__ = (CheckConstraint('xp_per_task >= 0 AND coins_per_task >= 0',name='ck_reward_nonnegative'),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'),primary_key=True)
    xp_per_task: Mapped[int] = mapped_column(Integer,nullable=False,default=10)
    coins_per_task: Mapped[int] = mapped_column(Integer,nullable=False,default=5)
    rule_version: Mapped[int] = mapped_column(Integer,nullable=False,default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())

class RewardEntry(Base):
    __tablename__ = 'reward_entries'
    __table_args__ = (
        ForeignKeyConstraint(['task_id','user_id'],['tasks.id','tasks.user_id'],name='fk_reward_task_owner'),
        UniqueConstraint('id','user_id',name='uq_reward_id_user'),
        UniqueConstraint('source_event_id',name='uq_reward_source_event'),
        ForeignKeyConstraint(['source_event_id','user_id'],['task_events.id','task_events.user_id'],name='fk_reward_event_owner'),
        UniqueConstraint('reversal_of',name='uq_reward_reversal'),
        ForeignKeyConstraint(['reversal_of','user_id'],['reward_entries.id','reward_entries.user_id'],name='fk_reward_reversal_owner'),
        CheckConstraint("kind IN ('grant','reversal')",name='ck_reward_kind'),
        CheckConstraint("(kind='grant' AND reversal_of IS NULL AND xp_delta >= 0 AND coin_delta >= 0) OR (kind='reversal' AND reversal_of IS NOT NULL AND xp_delta <= 0 AND coin_delta <= 0)",name='ck_reward_deltas'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True,default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'),nullable=False,index=True)
    task_id: Mapped[UUID] = mapped_column(nullable=False,index=True)
    source_event_id: Mapped[UUID] = mapped_column(nullable=False)
    reversal_of: Mapped[UUID | None] = mapped_column()
    kind: Mapped[str] = mapped_column(String(16),nullable=False)
    xp_delta: Mapped[int] = mapped_column(Integer,nullable=False)
    coin_delta: Mapped[int] = mapped_column(Integer,nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now())
