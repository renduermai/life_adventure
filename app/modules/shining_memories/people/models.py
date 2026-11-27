from datetime import date, datetime
from uuid import UUID, uuid4
from sqlalchemy import String, Text, Integer, Date, DateTime, Boolean, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class MemoryPerson(Base):
    __tablename__ = 'memory_people'
    __table_args__ = (
        UniqueConstraint('id','user_id',name='uq_memory_person_owner'),
        UniqueConstraint('user_id','create_request_id',name='uq_memory_person_request'),
        CheckConstraint("contact_preference IN ('unspecified','willing','hesitant','no_contact')",name='ck_memory_contact_preference'),
        CheckConstraint('version >= 1',name='ck_memory_person_version'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True,default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'),index=True)
    name: Mapped[str] = mapped_column(String(120))
    relationship: Mapped[str] = mapped_column(String(120))
    precious_moments: Mapped[str] = mapped_column(Text,default='')
    manual_contact_date: Mapped[date|None] = mapped_column(Date)
    contact_preference: Mapped[str] = mapped_column(String(16),default='unspecified')
    notes: Mapped[str] = mapped_column(Text,default='')
    version: Mapped[int] = mapped_column(Integer,default=1,server_default=text('1'))
    create_request_id: Mapped[UUID] = mapped_column()
    create_fingerprint: Mapped[str] = mapped_column(String(64))
    deleted_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now())


class MemoryPersonEvent(Base):
    __tablename__ = 'memory_person_events'
    __table_args__ = (
        ForeignKeyConstraint(['person_id','user_id'],['memory_people.id','memory_people.user_id'],name='fk_memory_event_owner'),
        UniqueConstraint('user_id','create_request_id',name='uq_memory_event_request'),
        CheckConstraint('version >= 1',name='ck_memory_event_version'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True,default=uuid4)
    person_id: Mapped[UUID] = mapped_column(index=True)
    user_id: Mapped[UUID] = mapped_column()
    event_date: Mapped[date] = mapped_column(Date)
    content: Mapped[str] = mapped_column(Text)
    is_actual_contact: Mapped[bool] = mapped_column(Boolean)
    version: Mapped[int] = mapped_column(Integer,default=1,server_default=text('1'))
    create_request_id: Mapped[UUID] = mapped_column()
    create_fingerprint: Mapped[str] = mapped_column(String(64))
    deleted_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now())
