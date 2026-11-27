from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Kind = Literal['talent', 'signal']
Strength = Literal['强', '较强', '已有外部信号', '中等', '正在形成', '待验证']
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)


class Submit(Strict):
    original: str = Field(min_length=1, max_length=10000)

    @field_validator('original')
    @classmethod
    def usable_text(cls, value):
        if not value.strip() or any(ord(c) < 32 and c not in '\t\r\n' for c in value):
            raise ValueError('请输入有效原文')
        return value


class Resolve(Strict):
    choice: Literal['merge', 'separate']


class Anchored(Strict):
    evidence_id: str | None = Field(default=None, max_length=20)
    quote: str = Field(default='', max_length=200)


class Finding(Anchored):
    kind: Kind
    label: Label
    summary: str = Field(min_length=1, max_length=200)
    strength: Strength | None
    reason: str = Field(min_length=1, max_length=220)
    match: Literal['new', 'same', 'uncertain']
    existing_id: UUID | None
    related_talents: list[Label] = Field(max_length=4)

    @model_validator(mode='after')
    def consistent_fields(self):
        if (self.kind == 'talent') != (self.strength is not None):
            raise ValueError('只有天赋需要强度标签')
        if (self.match == 'new') != (self.existing_id is None):
            raise ValueError('匹配判断缺少有效的关联编号')
        if any(not text.strip() for text in (self.reason, self.summary)):
            raise ValueError('发现不得使用空白依据')
        if any(ord(c) < 32 for c in self.label) or any('\x00' in text for text in
                                                   (self.reason, self.summary)):
            raise ValueError('发现包含无效字符')
        return self


class Cultivation(Anchored):
    talent: Label
    advantage: str = Field(min_length=1, max_length=160)
    risk: str = Field(min_length=1, max_length=160)
    totem: bool = Field(default=False, strict=True)


class Direction(Anchored):
    kind: Literal['career', 'long_term']
    title: Label
    horizon: str = Field(default='', max_length=60)
    reason: str = Field(min_length=1, max_length=200)
    next_step: str = Field(min_length=1, max_length=160)
    previous_key: str | None = Field(default=None, max_length=64)


class Development(Strict):
    cultivation: list[Cultivation] = Field(default_factory=list, max_length=6)
    directions: list[Direction] = Field(default_factory=list, max_length=6)


class ProbeResult(Development):
    findings: list[Finding] = Field(max_length=10)

class EntryEdit(Strict):
    strength: Strength | None = None
    label: Label
    summary: str = Field(min_length=1, max_length=200)


class ObservationEdit(EntryEdit):
    reason: str = Field(min_length=1, max_length=220)


class CultivationEdit(Strict):
    advantage: str = Field(min_length=1, max_length=160)
    risk: str = Field(min_length=1, max_length=160)


class DirectionEdit(Strict):
    title: Label
    horizon: str = Field(default='', max_length=60)
    reason: str = Field(min_length=1, max_length=200)
    next_step: str = Field(min_length=1, max_length=160)

class OutlineSection(Strict):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    segments: list[str] = Field(min_length=1, max_length=175)


class TextOutline(Strict):
    sections: list[OutlineSection] = Field(max_length=16)
