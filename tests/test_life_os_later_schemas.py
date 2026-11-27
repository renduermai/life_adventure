from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.modules.life_os import later_service
from app.modules.life_os.later_schemas import ExperienceInput, SceneInput


def test_experience_layer_belongs_to_selected_model():
    base={'model':'life','layer':'生活秩序','occurred_on':'2026-11-26','event':'synthetic event','experience':'synthetic experience'}
    assert ExperienceInput.model_validate(base).layer=='生活秩序'
    with pytest.raises(ValidationError):ExperienceInput.model_validate(base|{'layer':'安全'})


@pytest.mark.parametrize('offset',[0,None])
def test_cross_midnight_must_be_explicit(offset):
    with pytest.raises((ValidationError,TypeError)):
        SceneInput(name='synthetic',daily_slots=[{'start':'22:00','end':'02:00','end_day_offset':offset,'activity':'sleep'}])


def test_current_and_next_around_midnight_use_timezone(monkeypatch):
    sid=str(uuid4());uid=uuid4()
    monkeypatch.setattr(later_service,'scene_list',lambda *args:{'items':[{'id':sid,'daily_slots':[
        {'start':'02:30','end':'03:00','end_day_offset':0,'activity':'wake','fixed':False},
        {'start':'22:00','end':'02:00','end_day_offset':1,'activity':'sleep','fixed':True}],
        'weekly_rhythm':[]}],'active_id':sid})
    result=later_service.scene_current(None,uid,'Asia/Shanghai',datetime(2026,11,26,1,0,tzinfo=ZoneInfo('Asia/Shanghai')))
    assert result['current']['activity']=='sleep'
    assert result['next']['activity']=='wake'
    assert result['minute_of_day']==60
