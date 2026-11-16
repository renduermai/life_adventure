from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


class Create(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    content: str = Field(min_length=1, max_length=5000)

    @field_validator('content')
    @classmethod
    def meaningful(cls, value):
        if not value.strip() or '\x00' in value:
            raise ValueError('需要非空且不含空字符的原文')
        return value


class Delete(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: StrictInt = Field(ge=1)
