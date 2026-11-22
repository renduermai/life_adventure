from datetime import date
from decimal import Decimal
from uuid import UUID
from pydantic import Field,field_validator,model_validator
from ..people.schemas import Strict

class Fields(Strict):
    name:str=Field(min_length=1,max_length=120)
    purchase_date:date
    is_entitlement:bool=Field(default=False,strict=True)
    expires_at:date|None=None
    @model_validator(mode='after')
    def entitlement(self):
        if self.is_entitlement:
            if self.expires_at is None or self.expires_at<self.purchase_date:raise ValueError('权益到期日期必填且不能早于购买日期')
        elif self.expires_at is not None:raise ValueError('普通物品到期日期必须为空')
        return self
    purchase_price:Decimal=Field(ge=0,max_digits=14,decimal_places=2,allow_inf_nan=False)
    category:str=Field(default='',max_length=120)
    image_asset_id:UUID|None=None
    @field_validator('name','category')
    @classmethod
    def text(cls,value,info):
        if any(ord(c)<32 for c in value) or (info.field_name=='name' and not value.strip()):raise ValueError('字段无效')
        return value.strip()

class Create(Fields):request_id:UUID
class Edit(Fields):expected_version:int=Field(ge=1)
