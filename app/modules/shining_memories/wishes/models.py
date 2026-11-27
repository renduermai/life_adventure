from datetime import datetime
from decimal import Decimal
from uuid import UUID,uuid4
from sqlalchemy import String,Text,Numeric,DateTime,Integer,JSON,ForeignKey,ForeignKeyConstraint,UniqueConstraint,CheckConstraint,func,text
from sqlalchemy.orm import Mapped,mapped_column
from app.core.database import Base

class MemoryWish(Base):
    __tablename__='memory_wishes'
    __table_args__=(UniqueConstraint('id','user_id',name='uq_memory_wish_owner'),
        UniqueConstraint('user_id','create_request_id',name='uq_memory_wish_request'),
        ForeignKeyConstraint(['image_asset_id','user_id'],['memory_assets.id','memory_assets.user_id'],name='fk_memory_wish_image_owner'),
        UniqueConstraint('image_asset_id',name='uq_memory_wish_image'),
        CheckConstraint("currency = 'CNY' AND initial_price >= 0 AND current_price >= 0 AND version >= 1",name='ck_memory_wish_values'))
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
    name:Mapped[str]=mapped_column(String(120))
    description:Mapped[str]=mapped_column(Text,default='')
    reason:Mapped[str]=mapped_column(Text,default='')
    initial_price:Mapped[Decimal]=mapped_column(Numeric(14,2))
    current_price:Mapped[Decimal]=mapped_column(Numeric(14,2))
    currency:Mapped[str]=mapped_column(String(3),default='CNY',server_default=text("'CNY'"))
    category:Mapped[str]=mapped_column(String(120),default='')
    category_source:Mapped[str]=mapped_column(String(12),default='manual')
    image_asset_id:Mapped[UUID|None]=mapped_column()
    version:Mapped[int]=mapped_column(Integer,default=1,server_default=text('1'))
    create_request_id:Mapped[UUID]=mapped_column()
    create_fingerprint:Mapped[str]=mapped_column(String(64))
    deleted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class WishPrice(Base):
    __tablename__='memory_wish_prices'
    __table_args__=(ForeignKeyConstraint(['wish_id','user_id'],['memory_wishes.id','memory_wishes.user_id'],name='fk_memory_wish_price_owner'),
        UniqueConstraint('user_id','request_id',name='uq_memory_wish_price_request'),
        CheckConstraint("kind IN ('initial','update','correction') AND price >= 0",name='ck_memory_wish_price'))
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    wish_id:Mapped[UUID]=mapped_column(index=True)
    user_id:Mapped[UUID]=mapped_column()
    request_id:Mapped[UUID]=mapped_column()
    fingerprint:Mapped[str]=mapped_column(String(64))
    kind:Mapped[str]=mapped_column(String(12))
    price:Mapped[Decimal]=mapped_column(Numeric(14,2))
    previous_price:Mapped[Decimal|None]=mapped_column(Numeric(14,2))
    note:Mapped[str]=mapped_column(String(500),default='')
    recorded_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class WishClassification(Base):
    __tablename__='memory_wish_classifications'
    __table_args__=(ForeignKeyConstraint(['wish_id','user_id'],['memory_wishes.id','memory_wishes.user_id'],name='fk_memory_wish_ai_owner'),
        UniqueConstraint('user_id','request_id',name='uq_memory_wish_ai_request'),
        CheckConstraint("state IN ('running','succeeded','failed')",name='ck_memory_wish_ai_state'))
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    wish_id:Mapped[UUID]=mapped_column(index=True)
    user_id:Mapped[UUID]=mapped_column()
    request_id:Mapped[UUID]=mapped_column()
    fingerprint:Mapped[str]=mapped_column(String(64))
    state:Mapped[str]=mapped_column(String(12))
    result:Mapped[dict|None]=mapped_column(JSON)
    error_code:Mapped[str|None]=mapped_column(String(60))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
