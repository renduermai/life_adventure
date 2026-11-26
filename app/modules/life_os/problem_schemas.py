from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from .schemas import Strict,Output

class ProblemProposal(Strict):
    existing_id:UUID|None
    name:str=Field(min_length=1,max_length=80)
    mechanism:str=Field(max_length=200)
    observation:str=Field(max_length=200)

class EventProposal(Strict):
    relation:Literal['new','continue','uncertain']
    existing_event_id:UUID|None
    title:str=Field(min_length=1,max_length=160)
    evidence_quote:str=Field(min_length=1,max_length=300)
    action_quote:str=Field(max_length=300)
    feedback_quote:str=Field(max_length=300)
    outcome:Literal['unknown','helpful','unhelpful','mixed']
    problems:list[ProblemProposal]=Field(max_length=3)
    @model_validator(mode='after')
    def facts(self):
        if self.relation=='continue' and self.existing_event_id is None:raise ValueError('继续事件需要ID')
        if self.relation in ('new','uncertain') and self.existing_event_id is not None:raise ValueError('新事件不能指定已有ID')
        if not self.feedback_quote and self.outcome!='unknown':raise ValueError('没有反馈不能判断效果')
        return self

class ProblemOutput(Output):
    # Keep valid core state if only the optional event fields are malformed.
    event:EventProposal|dict|None=Field(default=None,union_mode="left_to_right")

class EditProblem(Strict):
    request_id:UUID
    expected_version:int=Field(ge=1,strict=True)
    name:str=Field(min_length=1,max_length=80)
    mechanism:str=Field(max_length=1000)
    notes:str=Field(max_length=2000)

class Version(Strict):
    request_id:UUID
    expected_version:int=Field(ge=1,strict=True)

class Merge(Version):
    target_id:UUID
    target_version:int=Field(ge=1,strict=True)

class EditEvent(Version):
    title:str=Field(min_length=1,max_length=160)
    occurred_at:datetime
    status:Literal['confirmed','pending']
    problem_ids:list[UUID]=Field(max_length=20)
    @model_validator(mode='after')
    def aware(self):
        if self.occurred_at.tzinfo is None:raise ValueError('日期需要时区')
        if len(set(self.problem_ids))!=len(self.problem_ids):raise ValueError('重复问题')
        return self

class MoveSource(Strict):
    request_id:UUID
    source_id:UUID
    expected_event_id:UUID
    expected_version:int=Field(ge=1,strict=True)
    target_event_id:UUID|None=None
    title:str=Field(default='',max_length=160)

class Feedback(Strict):
    request_id:UUID
    action:str=Field(max_length=1000)
    feedback:str=Field(max_length=1000)
    outcome:Literal['unknown','helpful','unhelpful','mixed']='unknown'
    @model_validator(mode='after')
    def evidence(self):
        if not self.action.strip() and not self.feedback.strip():raise ValueError('需要行动或反馈')
        if not self.feedback.strip() and self.outcome!='unknown':raise ValueError('没有反馈不能确定效果')
        return self

class ImportNote(Strict):
    request_id:UUID
    note_id:UUID
    event_id:UUID|None=None
    title:str=Field(min_length=1,max_length=160)
    problem_ids:list[UUID]=Field(max_length=20)
