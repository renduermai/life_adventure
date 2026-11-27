"""PostgreSQL integration tests for life operating steps four through six."""
from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.modules.life_os.models import Analysis, Message
from app.modules.life_os import later_service
from app.modules.life_os.later_models import LayerExperience, LifeScene, OperatingModeHistory
from app.modules.life_os.later_schemas import SceneInput
from test_distractions_postgres import notes
from test_tasks_postgres import task_engine

pytestmark=pytest.mark.integration
BASE='/api/life-os'
HEADERS={'Origin':'http://testserver'}


def test_layer_experience_crud_history_and_owner_scope(notes):
    client,sessions,owner,other,_=notes
    payload={'model':'life','layer':'生活秩序','occurred_on':'2026-11-26','event':'桌面堆满物品','experience':'清理一个角落后更容易开始工作','recommendation':'先清理桌面的一小块','notes':'合成测试'}
    created=client.post(BASE+'/layers/experiences',headers=HEADERS,json=payload)
    assert created.status_code==200,created.text
    eid=created.json()['id']
    assert len(client.get(BASE+'/layers/experiences?model=life&layer=生活秩序').json()['items'])==1
    updated=client.put(BASE+'/layers/experiences/'+eid,headers=HEADERS,json=payload|{'experience':'合成编辑后更容易行动'})
    assert updated.status_code==200 and updated.json()['version']==2
    assert [x['version'] for x in client.get(BASE+'/layers/experiences/'+eid+'/history').json()['items']]==[2,1]
    client.cookies.set('camp_session',str(other))
    assert client.get(BASE+'/layers/experiences?model=life&layer=生活秩序').json()['items']==[]
    assert client.get(BASE+'/layers/experiences/'+eid+'/history').status_code==404
    assert client.delete(BASE+'/layers/experiences/'+eid,headers=HEADERS).status_code==404
    client.cookies.set('camp_session',str(owner))
    assert client.delete(BASE+'/layers/experiences/'+eid,headers=HEADERS).json()['deleted'] is True
    assert client.get(BASE+'/layers/experiences?model=life&layer=生活秩序').json()['items']==[]
    with sessions() as db:
        row=db.get(LayerExperience,UUID(eid));assert row.deleted_at and row.version==3


def test_modes_preserve_manual_choice_and_record_ai_suggestions(notes):
    client,sessions,owner,_,_=notes
    assert client.get(BASE+'/mode').json()['actual_mode'] is None
    chosen=client.post(BASE+'/mode',headers=HEADERS,json={'mode':'blue'});assert chosen.status_code==200
    with sessions.begin() as db:
        message=Message(user_id=owner,request_id=uuid4(),content='合成状态原文');db.add(message);db.flush()
        analysis=Analysis(user_id=owner,message_id=message.id,request_id=uuid4(),status='succeeded',result={'suggested_mode':'red','core_conflict':'合成依据'},source_ids=[str(message.id)],prompt_version='test',finished_at=datetime.now(ZoneInfo('UTC')))
        db.add(analysis);db.flush();later_service.apply_analysis_mode(db,owner,analysis)
    state=client.get(BASE+'/mode').json()
    assert state['actual_mode']=='blue' and state['suggested_mode']=='red' and state['follows_ai'] is False
    assert client.post(BASE+'/mode/follow-ai',headers=HEADERS).json()['actual_mode']=='red'
    assert len(client.get(BASE+'/mode').json()['history'])>=3
    with sessions() as db:assert len(list(db.scalars(select(OperatingModeHistory).where(OperatingModeHistory.user_id==owner))))>=3


def test_scenes_daily_weekly_cross_midnight_history_and_owner_scope(notes):
    client,sessions,owner,other,_=notes
    payload={'name':'测试待业期','daily_slots':[{'start':'02:30','end':'03:00','end_day_offset':0,'activity':'起床','fixed':False},{'start':'22:00','end':'02:00','end_day_offset':1,'activity':'睡眠','fixed':True}],'weekly_rhythm':[{'weekday':0,'period':'daytime','activity':'技术学习','fixed':False},{'weekday':5,'period':'evening','activity':'社交','fixed':False}]}
    created=client.post(BASE+'/scenes',headers=HEADERS,json=payload);assert created.status_code==200,created.text
    sid=created.json()['id'];assert client.get(BASE+'/scenes').json()['active_id']==sid
    current=later_service.scene_current(client.app.state.database,owner,'Asia/Shanghai',datetime(2026,11,26,1,0,tzinfo=ZoneInfo('Asia/Shanghai')))
    assert current['current']['activity']=='睡眠' and current['next']['activity']=='起床'
    assert current['minute_of_day']==60 and current['day_progress']>4
    copy=client.post(BASE+f'/scenes/{sid}/copy',headers=HEADERS,json={'name':'测试工作日副本','daily_slots':payload['daily_slots'],'weekly_rhythm':payload['weekly_rhythm']})
    assert copy.status_code==200,copy.text
    copy_id=copy.json()['id'];assert copy.json()['daily_slots']==payload['daily_slots']
    updated=client.put(BASE+f'/scenes/{copy_id}',headers=HEADERS,json=payload|{'name':'修改场景'})
    assert updated.status_code==200 and updated.json()['version']==2
    assert len(client.get(BASE+f'/scenes/{copy_id}/history').json()['items'])==2
    client.cookies.set('camp_session',str(other));assert client.get(BASE+'/scenes').json()['items']==[]
    assert client.delete(BASE+f'/scenes/{sid}',headers=HEADERS).status_code==404
    client.cookies.set('camp_session',str(owner));assert client.delete(BASE+f'/scenes/{copy_id}',headers=HEADERS).json()['deleted'] is True
    with sessions() as db:assert db.get(LifeScene,UUID(copy_id)).deleted_at is not None


def test_schedule_validation_rejects_implicit_cross_midnight():
    with pytest.raises(Exception):
        SceneInput(name='非法跨午夜',daily_slots=[{'start':'22:00','end':'02:00','end_day_offset':0,'activity':'睡觉'}])
