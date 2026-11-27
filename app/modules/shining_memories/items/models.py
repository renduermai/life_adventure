from datetime import date,datetime
from decimal import Decimal
from uuid import UUID,uuid4
from sqlalchemy import Boolean,String,Numeric,Date,DateTime,Integer,ForeignKey,ForeignKeyConstraint,UniqueConstraint,CheckConstraint,func,text
from sqlalchemy.orm import Mapped,mapped_column
from app.core.database import Base

class MemoryItem(Base):
    __tablename__='memory_items'
    __table_args__=(ForeignKeyConstraint(['image_asset_id','user_id'],['memory_assets.id','memory_assets.user_id'],name='fk_memory_item_image_owner'),
        UniqueConstraint('user_id','create_request_id',name='uq_memory_item_request'),
        UniqueConstraint('image_asset_id',name='uq_memory_item_image'),
        CheckConstraint('purchase_price >= 0',name='ck_memory_item_price'),
        CheckConstraint("currency = 'CNY'",name='ck_memory_item_currency'),
        CheckConstraint('version >= 1',name='ck_memory_item_version'),
        CheckConstraint('(is_entitlement AND expires_at IS NOT NULL AND expires_at >= purchase_date) OR (NOT is_entitlement AND expires_at IS NULL)',name='ck_memory_item_entitlement'))
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
    name:Mapped[str]=mapped_column(String(120))
    purchase_date:Mapped[date]=mapped_column(Date)
    is_entitlement:Mapped[bool]=mapped_column(Boolean,default=False,server_default=text('false'))
    expires_at:Mapped[date|None]=mapped_column(Date)
    purchase_price:Mapped[Decimal]=mapped_column(Numeric(14,2))
    currency:Mapped[str]=mapped_column(String(3),default='CNY',server_default=text("'CNY'"))
    category:Mapped[str]=mapped_column(String(120),default='')
    image_asset_id:Mapped[UUID|None]=mapped_column()
    version:Mapped[int]=mapped_column(Integer,default=1,server_default=text('1'))
    create_request_id:Mapped[UUID]=mapped_column()
    create_fingerprint:Mapped[str]=mapped_column(String(64))
    deleted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
