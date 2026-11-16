from uuid import UUID
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, StrictInt, HttpUrl, TypeAdapter, field_validator, model_validator


class Target(BaseModel):
    model_config = ConfigDict(extra='forbid')
    main_quest_id: UUID | None = None
    task_id: UUID | None = None

    @model_validator(mode='after')
    def exactly_one(self):
        if (self.main_quest_id is None) == (self.task_id is None):
            raise ValueError('必须且只能关联一个主线或副本')
        return self


class Create(Target):
    request_id: UUID
    description: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=2048)

    @field_validator('description')
    @classmethod
    def description_valid(cls, value):
        if not value.strip() or '\x00' in value:
            raise ValueError('描述不能为空')
        return value

    @field_validator('url')
    @classmethod
    def url_valid(cls, value):
        if any(c.isspace() or ord(c)<32 or ord(c)==127 for c in value) or '\\' in value:
            raise ValueError('链接包含非法字符')
        split = urlsplit(value)
        if split.scheme.lower() not in {'http','https'} or not split.netloc or not split.hostname:
            raise ValueError('需要完整HTTP或HTTPS地址')
        parsed = TypeAdapter(HttpUrl).validate_python(value)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError('链接不允许包含账号密码')
        return value


class Update(Target):
    expected_version: StrictInt = Field(ge=1)


class Delete(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: StrictInt = Field(ge=1)
