"""Owner-scoped life layer experiences, operating mode, and original scenes."""
from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, ForeignKeyConstraint, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LayerExperience(Base):
    __tablename__ = "life_os_layer_experiences"
    __table_args__ = (UniqueConstraint("id", "user_id", name="uq_life_layer_experience_owner"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(20))
    layer: Mapped[str] = mapped_column(String(40))
    occurred_on: Mapped[date] = mapped_column(Date)
    event: Mapped[str] = mapped_column(String(1200))
    experience: Mapped[str] = mapped_column(String(1600))
    recommendation: Mapped[str] = mapped_column(String(1200), default="")
    notes: Mapped[str] = mapped_column(String(1200), default="")
    source: Mapped[str] = mapped_column(String(12), default="user")
    version: Mapped[int] = mapped_column(default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LayerExperienceRevision(Base):
    __tablename__ = "life_os_layer_experience_revisions"
    __table_args__ = (ForeignKeyConstraint(["experience_id","user_id"],["life_os_layer_experiences.id","life_os_layer_experiences.user_id"],ondelete="CASCADE"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    experience_id: Mapped[UUID] = mapped_column(index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column()
    action: Mapped[str] = mapped_column(String(12))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OperatingMode(Base):
    __tablename__ = "life_os_operating_modes"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    follows_ai: Mapped[bool] = mapped_column(Boolean, default=True)
    actual_mode: Mapped[str | None] = mapped_column(String(12))
    suggested_mode: Mapped[str | None] = mapped_column(String(12))
    reason: Mapped[str] = mapped_column(String(240), default="")
    analysis_id: Mapped[UUID | None] = mapped_column(ForeignKey("life_os_analyses.id", ondelete="SET NULL"))
    version: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OperatingModeHistory(Base):
    __tablename__ = "life_os_operating_mode_history"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column()
    action: Mapped[str] = mapped_column(String(20))
    actual_mode: Mapped[str | None] = mapped_column(String(12))
    suggested_mode: Mapped[str | None] = mapped_column(String(12))
    follows_ai: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(String(240), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LifeScene(Base):
    __tablename__ = "life_os_scenes"
    __table_args__ = (UniqueConstraint("id", "user_id", name="uq_life_scene_owner"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    daily_slots: Mapped[list] = mapped_column(JSON, default=list)
    weekly_rhythm: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActiveLifeScene(Base):
    __tablename__ = "life_os_active_scene"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    scene_id: Mapped[UUID] = mapped_column()
    __table_args__ = (UniqueConstraint("scene_id", "user_id", name="uq_life_active_scene_owner"), ForeignKeyConstraint(["scene_id","user_id"],["life_os_scenes.id","life_os_scenes.user_id"]))


class LifeSceneRevision(Base):
    __tablename__ = "life_os_scene_revisions"
    __table_args__ = (ForeignKeyConstraint(["scene_id","user_id"],["life_os_scenes.id","life_os_scenes.user_id"],ondelete="CASCADE"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    scene_id: Mapped[UUID] = mapped_column(index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column()
    action: Mapped[str] = mapped_column(String(12))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
