from datetime import datetime
from uuid import UUID,uuid4
from sqlalchemy import ForeignKeyConstraint,UniqueConstraint,CheckConstraint,String,JSON,DateTime,func
from sqlalchemy.orm import Mapped,mapped_column
from app.core.database import Base


class PersonAnalysis(Base):
    __tablename__='memory_person_analyses'
    __table_args__=(
        ForeignKeyConstraint(['person_id','user_id'],['memory_people.id','memory_people.user_id'],name='fk_memory_analysis_owner'),
        UniqueConstraint('user_id','request_id',name='uq_memory_analysis_request'),
        CheckConstraint("state IN ('running','succeeded','failed')",name='ck_memory_analysis_state'),
    )
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    person_id:Mapped[UUID]=mapped_column(index=True)
    user_id:Mapped[UUID]=mapped_column()
    request_id:Mapped[UUID]=mapped_column()
    fingerprint:Mapped[str]=mapped_column(String(64))
    scope:Mapped[dict]=mapped_column(JSON)
    state:Mapped[str]=mapped_column(String(12))
    result:Mapped[dict|None]=mapped_column(JSON)
    error_code:Mapped[str|None]=mapped_column(String(60))
    rule_version:Mapped[str]=mapped_column(String(20),default='contact-v1')
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
