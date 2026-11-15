from datetime import datetime
from uuid import UUID,uuid4
from sqlalchemy import String,Integer,JSON,DateTime,ForeignKey,ForeignKeyConstraint,CheckConstraint,UniqueConstraint,func
from sqlalchemy.orm import Mapped,mapped_column
from app.core.database import Base

class TaskAnalysis(Base):
 __tablename__='task_analysis_cache'
 __table_args__=(ForeignKeyConstraint(['quest_id','user_id'],['main_quests.id','main_quests.user_id']),ForeignKeyConstraint(['task_id','user_id'],['tasks.id','tasks.user_id']),CheckConstraint('(quest_id IS NULL) != (task_id IS NULL)',name='ck_analysis_target'),UniqueConstraint('user_id','target_key',name='uq_analysis_target'))
 id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
 user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
 quest_id:Mapped[UUID|None]=mapped_column()
 task_id:Mapped[UUID|None]=mapped_column()
 target_key:Mapped[str]=mapped_column(String(80))
 fingerprint:Mapped[str]=mapped_column(String(64))
 config_signature:Mapped[str]=mapped_column(String(100))
 features:Mapped[dict]=mapped_column(JSON)
 override:Mapped[dict|None]=mapped_column(JSON)
 version:Mapped[int]=mapped_column(Integer,default=1)

class RecommendationBatch(Base):
 __tablename__='recommendation_batches'
 __table_args__=(ForeignKeyConstraint(['snapshot_id','user_id'],['startup_state_snapshots.id','startup_state_snapshots.user_id']),UniqueConstraint('user_id','request_id',name='uq_recommend_request'))
 id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
 user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
 snapshot_id:Mapped[UUID]=mapped_column()
 request_id:Mapped[UUID]=mapped_column()
 generation:Mapped[int]=mapped_column(Integer)
 status:Mapped[str]=mapped_column(String(20))
 results:Mapped[list]=mapped_column(JSON,default=list)
 error_code:Mapped[str|None]=mapped_column(String(50))
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
