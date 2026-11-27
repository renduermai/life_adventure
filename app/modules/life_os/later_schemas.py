"""Strict inputs for life layer experiences, modes, and original schedules."""
from datetime import date, time
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from .schemas import Strict

LifeLayer = Literal['生存基本盘','生活秩序','精神生活','职业发展','长期发展']
NeedLayer = Literal['生理','安全','归属与爱','尊重','自我实现']
Mode = Literal['green','yellow','red','blue']


class ExperienceInput(Strict):
    model: Literal['life','need']
    layer: str = Field(min_length=1, max_length=40)
    occurred_on: date
    event: str = Field(min_length=1, max_length=1200)
    experience: str = Field(min_length=1, max_length=1600)
    recommendation: str = Field(default='', max_length=1200)
    notes: str = Field(default='', max_length=1200)

    @model_validator(mode='after')
    def layer_matches_model(self):
        choices = {'life': LifeLayer.__args__, 'need': NeedLayer.__args__}
        if self.layer not in choices[self.model]:
            raise ValueError('层次与模型不匹配')
        return self


class ModeInput(Strict):
    mode: Mode


class SceneInput(Strict):
    name: str = Field(min_length=1, max_length=80)
    daily_slots: list[dict] = Field(default_factory=list, max_length=80)
    weekly_rhythm: list[dict] = Field(default_factory=list, max_length=70)

    @field_validator('name')
    @classmethod
    def nonblank_name(cls, value):
        if not value.strip() or '\x00' in value:
            raise ValueError('请输入场景名称')
        return value.strip()

    @field_validator('daily_slots')
    @classmethod
    def valid_daily(cls, value):
        validated=[]
        for item in value:
            if not isinstance(item, dict) or set(item)-{'start','end','end_day_offset','activity','fixed'}:
                raise ValueError('每日时段字段无效')
            start=time.fromisoformat(item.get('start',''))
            if start.second or start.microsecond: raise ValueError('时间精确到分钟')
            end_value=item.get('end')
            end=time.fromisoformat(end_value) if end_value else None
            if end and (end.second or end.microsecond): raise ValueError('时间精确到分钟')
            offset=item.get('end_day_offset',0)
            if type(offset) is not int or offset not in (0,1): raise ValueError('结束日期偏移只能为0或1')
            if end and ((end<=start and offset!=1) or (end>start and offset!=0)):
                raise ValueError('跨午夜时请明确选择次日结束')
            if not end and offset: raise ValueError('无结束时间时不能设置结束日期偏移')
            activity=item.get('activity')
            fixed=item.get('fixed',False)
            if not isinstance(activity,str) or not activity.strip() or len(activity)>240 or '\x00' in activity: raise ValueError('活动内容无效')
            if not isinstance(fixed,bool): raise ValueError('固定安排标记无效')
            validated.append({'start':start.strftime('%H:%M'),'end':end.strftime('%H:%M') if end else None,'end_day_offset':offset,'activity':activity.strip(),'fixed':fixed})
        return validated

    @field_validator('weekly_rhythm')
    @classmethod
    def valid_weekly(cls, value):
        validated=[]
        for item in value:
            if not isinstance(item,dict) or set(item)-{'weekday','period','activity','fixed'}: raise ValueError('每周节律字段无效')
            day=item.get('weekday');period=item.get('period');activity=item.get('activity');fixed=item.get('fixed',False)
            if type(day) is not int or day not in range(7): raise ValueError('星期应为0至6')
            if period not in ('daytime','evening'): raise ValueError('时段应为白天或晚上')
            if not isinstance(activity,str) or not activity.strip() or len(activity)>240 or '\x00' in activity: raise ValueError('活动内容无效')
            if not isinstance(fixed,bool): raise ValueError('固定安排标记无效')
            validated.append({'weekday':day,'period':period,'activity':activity.strip(),'fixed':fixed})
        return sorted(validated,key=lambda x:(x['weekday'],0 if x['period']=='daytime' else 1))
