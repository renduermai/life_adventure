from typing import Literal,Annotated
from uuid import UUID
from pydantic import Field,model_validator,field_validator
from .schemas import Strict


class Scope(Strict):
    include_tasks:bool=Field(default=False,strict=True)
    include_notes:bool=Field(default=False,strict=True)
    task_ids:list[UUID]=Field(default_factory=list,max_length=5)
    quest_ids:list[UUID]=Field(default_factory=list,max_length=5)
    note_ids:list[UUID]=Field(default_factory=list,max_length=5)


class Analyze(Scope):
    request_id:UUID
    preview_token:str=Field(min_length=64,max_length=64)
    consent_external:bool=Field(default=False,strict=True)


class Evidence(Strict):
    source:str=Field(min_length=1,max_length=80)
    quote:str=Field(min_length=1,max_length=160)


class Judgment(Strict):
    level:Literal['none','some','strong']
    reason:str=Field(max_length=180)
    evidence:list[Evidence]=Field(max_length=3)


class Negative(Strict):
    severity:Literal['none','moderate','strong','defer']
    reason:str=Field(max_length=180)
    evidence:list[Evidence]=Field(max_length=3)


class Related(Strict):
    kind:Literal['quest','task','note']
    id:UUID
    reason:str=Field(min_length=1,max_length=180)
    evidence:list[Evidence]=Field(min_length=1,max_length=3)


class PersonOutput(Strict):
    meaning_label:str=Field(min_length=1,max_length=40)
    meaning_summary:str=Field(min_length=1,max_length=600)
    positive_factors:list[str]=Field(max_length=5)
    meaning:Judgment
    topic:Judgment
    goal:Judgment
    negative:Negative
    related:list[Related]=Field(max_length=10)
    contact_suggestion:str=Field(max_length=300)


# Old persisted results are read with PersonOutput; only new generation is compact.
class CompactEvidence(Evidence):
    quote:str=Field(min_length=1,max_length=40)

class CompactJudgment(Judgment):
    reason:str=Field(max_length=30)
    evidence:list[CompactEvidence]=Field(max_length=1)

class CompactNegative(Negative):
    reason:str=Field(max_length=60)
    evidence:list[CompactEvidence]=Field(max_length=1)
    @field_validator('reason')
    @classmethod
    def points(cls,value):
        if len([x for x in value.splitlines() if x.strip()])>3:raise ValueError('负面影响最多3点')
        return value

class CompactRelated(Related):
    reason:str=Field(min_length=1,max_length=40)
    evidence:list[CompactEvidence]=Field(min_length=1,max_length=1)

class CompactPersonOutput(PersonOutput):
    meaning_label:str=Field(min_length=1,max_length=20)
    meaning_summary:str=Field(min_length=1,max_length=150)
    positive_factors:list[Annotated[str,Field(min_length=1,max_length=35)]]=Field(max_length=3)
    meaning:CompactJudgment
    topic:CompactJudgment
    goal:CompactJudgment
    negative:CompactNegative
    related:list[CompactRelated]=Field(max_length=6)
    contact_suggestion:str=Field(max_length=150)
    @field_validator('contact_suggestion')
    @classmethod
    def suggestions(cls,value):
        if len([x for x in value.splitlines() if x.strip()])>3:raise ValueError('联系建议最多3条')
        return value
    @model_validator(mode='after')
    def links(self):
        if sum(x.kind in ('quest','task') for x in self.related)>3 or sum(x.kind=='note' for x in self.related)>3:
            raise ValueError('主副本关联最多3条，杂念关联最多3条')
        if len({(x.kind,x.id) for x in self.related})!=len(self.related):raise ValueError('关联不可重复')
        return self
