from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator
from app.modules.startup_chat.schemas import StateAdvice


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Step(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    detail: str = Field(max_length=600)
    minutes: StrictInt = Field(ge=1, le=240)
    done_when: str = Field(min_length=1, max_length=200)


class Advice(StrictModel):
    reply: str = Field(min_length=1, max_length=400)
    steps: list[Step] = Field(min_length=1, max_length=5)
    minimum_index: StrictInt = Field(ge=0, le=4)
    state_advice: StateAdvice | None = None

    @model_validator(mode='after')
    def minimum_exists(self):
        if self.minimum_index >= len(self.steps):
            raise ValueError('Minimum action must be a listed step')
        return self


class Generate(StrictModel):
    task_type: Literal['quest', 'task']
    task_id: UUID
    request_id: UUID
    previous_id: UUID | None = None
    expected_revision: StrictInt | None = Field(default=None, ge=1)
    feedback: str = Field(default='', max_length=2000)


class EditableStep(Step):
    id: UUID


class Edit(StrictModel):
    expected_revision: StrictInt = Field(ge=1)
    steps: list[EditableStep] = Field(min_length=1, max_length=5)
    minimum_id: UUID


class Confirm(StrictModel):
    expected_revision: StrictInt = Field(ge=1)
    mode: Literal['tasks', 'milestones', 'checklist']
    selected: list[UUID] = Field(min_length=1, max_length=5)
    reuse: dict[str, UUID] = Field(default_factory=dict)
    allow_duplicates: StrictBool = False
    confirmed: StrictBool


class Check(StrictModel):
    request_id: UUID
    expected_version: StrictInt = Field(ge=0)
    step_id: UUID
    checked: StrictBool


class Start(StrictModel):
    step_id: UUID
    create_task: StrictBool = False
    existing_task_id: UUID | None = None
