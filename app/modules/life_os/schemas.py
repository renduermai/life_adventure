from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)

class Send(Strict):
    request_id: UUID
    content: str = Field(default='',max_length=4000)
    note_ids: list[UUID] = Field(default_factory=list)
    @model_validator(mode='after')
    def valid_input(self):
        if '\x00' in self.content or (not self.content.strip() and not self.note_ids):raise ValueError('请填写想说的话或勾选杂念')
        return self

class Analyze(Strict):
    request_id: UUID
    consent_external: bool = Field(strict=True)
    note_ids: list[UUID] = Field(default_factory=list)

class Estimate(Strict):
    value: int | None = Field(ge=0,le=100,strict=True)
    reason: str = Field(min_length=1,max_length=100)

Short = Annotated[str,Field(min_length=1,max_length=160)]
class Output(Strict):
    reply: str = Field(min_length=1,max_length=600)
    energy: Estimate
    bandwidth: Estimate
    order: Estimate
    core_conflict: str = Field(max_length=180)
    triggers: list[Short] = Field(max_length=3)
    likely_behaviors: list[Short] = Field(max_length=3)
    behavior_contribution: str = Field(max_length=200)
    ideal_solution: str = Field(max_length=250)
    feasible_action: str = Field(max_length=200)
    life_layers: list[Literal['生存基本盘','生活秩序','精神生活','职业发展','长期发展']] = Field(max_length=5)
    need_layers: list[Literal['生理','安全','归属与爱','尊重','自我实现']] = Field(max_length=5)
    suggested_mode: Literal['green','yellow','red','blue','unknown']
    schedule_update_needed: bool = Field(strict=True)
    attractor_update_needed: bool = Field(strict=True)
    source_ids: list[UUID] = Field(min_length=1,max_length=20)

class Correct(Strict):
    request_id: UUID
    energy: int | None = Field(ge=0,le=100,strict=True)
    bandwidth: int | None = Field(ge=0,le=100,strict=True)
    order: int | None = Field(ge=0,le=100,strict=True)


class EditMessage(Strict):
    content: str = Field(min_length=1, max_length=120000)

    @model_validator(mode='after')
    def validate_content(self):
        if not self.content.strip() or chr(0) in self.content:
            raise ValueError('请输入有效原文')
        return self
