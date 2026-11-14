from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class StateSnapshot(Base):
    __tablename__ = "startup_state_snapshots"
    __table_args__ = (UniqueConstraint("id", "user_id", name="uq_state_owner"), UniqueConstraint("user_id", "request_id", name="uq_state_request"), CheckConstraint("pressure BETWEEN 0 AND 100 AND energy BETWEEN 0 AND 100", name="ck_state_values"))
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    request_id: Mapped[UUID] = mapped_column()
    fingerprint: Mapped[str] = mapped_column(String(64))
    pressure: Mapped[int] = mapped_column(Integer)
    energy: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[str] = mapped_column(String(2000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class StateCurrent(Base):
    __tablename__ = "startup_current"
    __table_args__ = (ForeignKeyConstraint(["snapshot_id", "user_id"], ["startup_state_snapshots.id", "startup_state_snapshots.user_id"], name="fk_state_current_owner"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column()
    generation: Mapped[int] = mapped_column(Integer, default=1)
