"""Distinct problems, occurrences, source links and append-only experience/history."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class Problem(Base):
    __tablename__='life_os_problems'
    __table_args__=(UniqueConstraint('id','user_id',name='uq_life_problem_owner'),UniqueConstraint('user_id','name_key',name='uq_life_problem_name'),)
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
    name:Mapped[str]=mapped_column(String(80))
    name_key:Mapped[str]=mapped_column(String(200))
    mechanism:Mapped[str]=mapped_column(String(1000),default='')
    notes:Mapped[str]=mapped_column(String(2000),default='')
    manual_fields:Mapped[list]=mapped_column(JSON,default=list)
    version:Mapped[int]=mapped_column(Integer,default=1)
    deleted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    merged_into:Mapped[UUID|None]=mapped_column()
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class LifeEvent(Base):
    __tablename__='life_os_events'
    __table_args__=(UniqueConstraint('id','user_id',name='uq_life_event_owner'),CheckConstraint("status IN ('confirmed','pending')",name='ck_life_event_status'))
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
    title:Mapped[str]=mapped_column(String(160))
    occurred_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    status:Mapped[str]=mapped_column(String(20))
    version:Mapped[int]=mapped_column(Integer,default=1)
    deleted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class EventSource(Base):
    __tablename__='life_os_event_sources'
    __table_args__=(ForeignKeyConstraint(['event_id','user_id'],['life_os_events.id','life_os_events.user_id']),ForeignKeyConstraint(['message_id','user_id'],['life_os_messages.id','life_os_messages.user_id']),ForeignKeyConstraint(['note_id','user_id'],['distraction_notes.id','distraction_notes.user_id']),UniqueConstraint('user_id','message_id',name='uq_life_event_message'),UniqueConstraint('user_id','note_id',name='uq_life_event_note'),CheckConstraint('(message_id IS NULL) <> (note_id IS NULL)',name='ck_life_source_one'))
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
    event_id:Mapped[UUID]=mapped_column()
    message_id:Mapped[UUID|None]=mapped_column()
    note_id:Mapped[UUID|None]=mapped_column()

class EventProblem(Base):
    __tablename__='life_os_event_problems'
    __table_args__=(ForeignKeyConstraint(['event_id','user_id'],['life_os_events.id','life_os_events.user_id']),ForeignKeyConstraint(['problem_id','user_id'],['life_os_problems.id','life_os_problems.user_id']))
    event_id:Mapped[UUID]=mapped_column(primary_key=True)
    problem_id:Mapped[UUID]=mapped_column(primary_key=True)
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))

class Experience(Base):
    __tablename__='life_os_experiences'
    __table_args__=(ForeignKeyConstraint(['event_id','user_id'],['life_os_events.id','life_os_events.user_id']),UniqueConstraint('user_id','dedup_key',name='uq_life_experience_dedup'),CheckConstraint("kind IN ('suggestion','observation','action','feedback')",name='ck_life_experience_kind'),CheckConstraint("outcome IN ('unknown','helpful','unhelpful','mixed')",name='ck_life_experience_outcome'))
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
    event_id:Mapped[UUID]=mapped_column()
    kind:Mapped[str]=mapped_column(String(20))
    text:Mapped[str]=mapped_column(String(1000))
    outcome:Mapped[str]=mapped_column(String(20),default='unknown')
    source_message_id:Mapped[UUID|None]=mapped_column(ForeignKey('life_os_messages.id'))
    source_quote:Mapped[str|None]=mapped_column(String(400))
    dedup_key:Mapped[str]=mapped_column(String(64))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class ProblemHistory(Base):
    __tablename__='life_os_problem_history'
    __table_args__=(UniqueConstraint('user_id','request_id',name='uq_life_history_request'),)
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
    target_id:Mapped[UUID]=mapped_column()
    action:Mapped[str]=mapped_column(String(40))
    request_id:Mapped[UUID]=mapped_column()
    fingerprint:Mapped[str]=mapped_column(String(64))
    before:Mapped[dict]=mapped_column(JSON)
    after:Mapped[dict]=mapped_column(JSON)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
