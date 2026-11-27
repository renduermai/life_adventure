from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictInt


class ItemFields(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    description: str = Field(min_length=1, max_length=2000)
    importance: StrictInt = Field(ge=0, le=100)
    urgency: StrictInt = Field(ge=0, le=100)
    progress: str = Field(default='', max_length=2000)


class Create(ItemFields):
    request_id: UUID


class Edit(ItemFields):
    expected_version: StrictInt = Field(ge=1)


class Delete(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: StrictInt = Field(ge=1)
