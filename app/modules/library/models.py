from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class LibraryLink(Base):
    __tablename__ = 'library_links'
    __table_args__ = (
        ForeignKeyConstraint(['main_quest_id','user_id'], ['main_quests.id','main_quests.user_id']),
        ForeignKeyConstraint(['task_id','user_id'], ['tasks.id','tasks.user_id']),
        CheckConstraint('(main_quest_id IS NULL) <> (task_id IS NULL)', name='ck_library_one_target'),
        CheckConstraint('click_count >= 0 AND version >= 1', name='ck_library_counters'),
        CheckConstraint('char_length(description) BETWEEN 1 AND 500', name='ck_library_description'),
        CheckConstraint('char_length(url) BETWEEN 1 AND 2048', name='ck_library_url_length'),
        UniqueConstraint('user_id','create_request_id', name='uq_library_create_request'),
        Index('ix_library_owner_sort','user_id','click_count','created_at','id'),
        Index('ix_library_quest','main_quest_id','user_id'),
        Index('ix_library_task','task_id','user_id'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    description: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(Text)
    main_quest_id: Mapped[UUID | None] = mapped_column()
    task_id: Mapped[UUID | None] = mapped_column()
    click_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default=text('0'))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text('1'))
    create_request_id: Mapped[UUID] = mapped_column()
    create_fingerprint: Mapped[str] = mapped_column(String(64))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
