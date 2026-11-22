from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,field_validator


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True)


class PersonFields(Strict):
    name:str=Field(min_length=1,max_length=120)
    relationship:str=Field(min_length=1,max_length=120)
    precious_moments:str=Field(default='',max_length=8000)
    manual_contact_date:date|None=None
    contact_preference:Literal['unspecified','willing','hesitant','no_contact']='unspecified'
    notes:str=Field(default='',max_length=2000)

    @field_validator('name','relationship')
    @classmethod
    def nonblank(cls,value):
        if not value.strip() or any(ord(c)<32 for c in value):raise ValueError('字段无效')
        return value.strip()


class PersonCreate(PersonFields):
    request_id:UUID


class PersonEdit(PersonFields):
    expected_version:int=Field(ge=1)


class Version(Strict):
    expected_version:int=Field(ge=1)


class EventFields(Strict):
    event_date:date
    content:str=Field(min_length=1,max_length=5000)
    is_actual_contact:bool=Field(strict=True)

    @field_validator('content')
    @classmethod
    def nonblank(cls,value):
        if not value.strip() or '\x00' in value:raise ValueError('事件不能为空')
        return value


class EventCreate(EventFields):
    request_id:UUID


class EventEdit(EventFields):
    expected_version:int=Field(ge=1)
