from decimal import Decimal
from uuid import UUID
from pydantic import Field,field_validator
from ..people.schemas import Strict

class Fields(Strict):
    name:str=Field(min_length=1,max_length=120)
    description:str=Field(default='',max_length=5000)
    reason:str=Field(default='',max_length=2000)
    category:str=Field(default='',max_length=120)
    image_asset_id:UUID|None=None
    @field_validator('name','category')
    @classmethod
    def valid(cls,value,info):
        if any(ord(c)<32 for c in value) or (info.field_name=='name' and not value.strip()):raise ValueError('字段无效')
        return value.strip()
class Create(Fields):
    request_id:UUID
    price:Decimal=Field(ge=0,max_digits=14,decimal_places=2,allow_inf_nan=False)
class Edit(Fields):expected_version:int=Field(ge=1)
class Price(Strict):
    request_id:UUID
    expected_version:int=Field(ge=1)
    price:Decimal=Field(ge=0,max_digits=14,decimal_places=2,allow_inf_nan=False)
class Correct(Price):
    note:str=Field(min_length=1,max_length=500)
    @field_validator('note')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('请说明纠正原因')
        return value
class Classify(Strict):
    request_id:UUID
    expected_version:int=Field(ge=1)
    consent_external:bool=Field(strict=True)
class Category(Strict):
    category:str=Field(min_length=1,max_length=120)
    reason:str=Field(max_length=300)
    @field_validator('category')
    @classmethod
    def nonblank(cls,value):
        if not value.strip() or any(ord(c)<32 for c in value):raise ValueError('类别无效')
        return value.strip()
