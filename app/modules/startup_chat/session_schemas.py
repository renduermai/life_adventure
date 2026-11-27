from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator
from app.modules.startup_chat.planning import Step


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class HistoryTurn(StrictModel):
    message: str = Field(min_length=1, max_length=2000)
    reply: str = Field(min_length=1, max_length=5000)


class CurrentState(StrictModel):
    pressure: StrictInt = Field(ge=0, le=100)
    energy: StrictInt = Field(ge=0, le=100)


class Message(StrictModel):
    request_id: UUID
    owner_id: UUID
    mode: Literal['free', 'breakdown']
    task_type: Literal['quest', 'task'] | None = None
    task_id: UUID | None = None
    message: str = Field(min_length=1, max_length=2000)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=6)
    state: CurrentState | None = None
    include_tasks: StrictBool = False

    @model_validator(mode='after')
    def valid_context(self):
        if self.mode == 'breakdown' and (not self.task_type or not self.task_id):
            raise ValueError('Breakdown requires a real target')
        if self.mode == 'free' and (self.task_type or self.task_id):
            raise ValueError('Free mode has no selected target')
        if sum(len(t.message)+len(t.reply) for t in self.history) > 12000:
            raise ValueError('History exceeds context budget')
        return self


class Reply(StrictModel):
    reply: str = Field(min_length=1, max_length=1200)
    needs_clarification: StrictBool
    understanding: str = Field(max_length=500)
    completed: str = Field(max_length=500)
    today_goal: str = Field(max_length=300)
    steps: list[Step] = Field(max_length=5)
    minimum_action: str = Field(max_length=300)

    @model_validator(mode='after')
    def clarify_before_steps(self):
        if self.needs_clarification and self.steps:
            raise ValueError('Ask missing information before producing steps')
        return self
