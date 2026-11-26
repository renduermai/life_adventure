from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)

class Send(Strict):
    request_id: UUID
    content: str = Field(min_length=1,max_length=4000)
    @field_validator('content')
    @classmethod
    def nonblank(cls,value):
        if not value.strip() or '\x00' in value: raise ValueError('请输入有效文字')
        return value

class Analyze(Strict):
    request_id: UUID
    consent_external: bool = Field(strict=True)
    note_ids: list[UUID] = Field(default_factory=list,max_length=3)

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
    source_ids: list[UUID] = Field(min_length=1,max_length=7)

class Correct(Strict):
    request_id: UUID
    energy: int | None = Field(ge=0,le=100,strict=True)
    bandwidth: int | None = Field(ge=0,le=100,strict=True)
    order: int | None = Field(ge=0,le=100,strict=True)
