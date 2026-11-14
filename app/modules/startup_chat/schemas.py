from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator


class MessageInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_id: UUID
    conversation_id: UUID | None = None
    expected_version: StrictInt = Field(ge=0)
    message: str = Field(min_length=1, max_length=2000)


class StateAdvice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reply: str = Field(min_length=1, max_length=200)
    ready: StrictBool
    pressure: StrictInt | None = Field(ge=0, le=100)
    energy: StrictInt | None = Field(ge=0, le=100)
    difficulty: str = Field(max_length=160)
    barrier: str = Field(max_length=80)
    goal: str = Field(max_length=80)

    @model_validator(mode='after')
    def enough_information(self):
        if self.ready and (self.pressure is None or self.energy is None):
            raise ValueError('A ready suggestion needs both values')
        return self
