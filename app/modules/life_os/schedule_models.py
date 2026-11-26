"""Immutable paired daily/weekly suggestions and failed attempts."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class ScheduleRun(Base):
    __tablename__='life_os_schedule_runs'
    id: Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    user_id: Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
    fingerprint: Mapped[str]=mapped_column(String(64),index=True)
    status: Mapped[str]=mapped_column(String(20))
    error_code: Mapped[str | None]=mapped_column(String(50))
    context: Mapped[dict]=mapped_column(JSON)
    result: Mapped[dict | None]=mapped_column(JSON)
    usage: Mapped[dict | None]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
