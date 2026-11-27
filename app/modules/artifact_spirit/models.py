from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FeatureVisit(Base):
    __tablename__ = 'feature_visits'

    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), primary_key=True)
    feature: Mapped[str] = mapped_column(String(40), primary_key=True)
    visited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
