from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from app.modules.ai_gateway.security import base_url


class ConfigFields(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(max_length=500)
    model_id: str = Field(min_length=1, max_length=160)
    protocol: Literal['openai_compatible'] = 'openai_compatible'
    expires_on: date | None = None
    notes: str = Field(default='', max_length=2000)
    enabled: bool = True

    @field_validator('base_url')
    @classmethod
    def url(cls, value):
        return base_url(value)

    @field_validator('name', 'model_id')
    @classmethod
    def text(cls, value):
        if not value.strip() or any(ord(c)<32 for c in value):
            raise ValueError('字段无效')
        return value.strip()


class CreateConfig(ConfigFields):
    request_id: UUID
    api_key: SecretStr = Field(min_length=8, max_length=4096)


class EditConfig(ConfigFields):
    expected_version: int = Field(ge=1)
    api_key: SecretStr | None = Field(default=None, max_length=4096)


class Version(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    expected_version: int = Field(ge=1)


class TestConnection(Version):
    request_id: UUID


class Binding(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    config_id: UUID | None
