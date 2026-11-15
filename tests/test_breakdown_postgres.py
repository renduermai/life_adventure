from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func
from app.modules.startup_chat import breakdown_service as service
from app.modules.startup_chat.breakdown_schemas import Advice,Generate,Edit
from app.modules.startup_chat.breakdown_models import BreakdownPlan
from app.modules.startup_state.models import StateCurrent
from app.modules.tasks import service as tasks
from app.modules.tasks.models import Task,TaskCommand
from app.modules.quests.models import Milestone,QuestEvent
from app.modules.growth.models import RewardEntry
from app.modules.ai_gateway.security import AIError
from test_ai_postgres import ai,make,task_engine,camp
from test_breakdown import advice

pytestmark=pytest.mark.integration
HEADERS={'Origin':'http://testserver'}


@pytest.fixture
def provider(monkeypatch):
    calls=[]
    def fake(self,uid,purpose,messages,request_id,output_schema=None,**kw):
        calls.append(messages)
        return {'content':Advice(**advice())}
    monkeypatch.setattr(service.AIService,'generate',fake)
    return calls


def create(camp,**values):
    with camp['sessions'].begin() as db:return tasks.execute(db,camp['user'],uuid4(),'create',{'title':'目标副本',**values})


def gen(client,tid,kind='task',previous=None,**extra):
    return client.post('/api/startup/breakdowns',headers=HEADERS,json=dict(task_type=kind,task_id=str(tid),request_id=str(uuid4()),previous_id=previous['id'] if previous else None,expected_revision=previous['revision'] if previous else None,feedback='再拆小一点' if previous else '')|extra)


def confirm(client,p,mode='tasks',**extra):
    return client.post('/api/startup/breakdowns/'+p['id']+'/confirm',headers=HEADERS,json=dict(expected_revision=p['revision'],mode=mode,selected=[s['id'] for s in p['advice']['steps']],reuse={},allow_duplicates=False,confirmed=True)|extra)


def test_generate_edit_confirm_repeat_and_focus(ai,provider):
    camp,settings,app,client=ai;tid=create(camp)
    rid=str(uuid4());p=gen(client,tid,request_id=rid).json()
    assert p['status']=='draft' and len(provider)==1
    assert gen(client,tid,request_id=rid).json()['id']==p['id']
    assert gen(client,tid).json()['id']==p['id'] and len(provider)==1
    with camp['sessions']() as db:assert db.scalar(select(func.count()).select_from(Task).where(Task.parent_task_id==tid))==0
    steps=p['advice']['steps'];steps[0]['title']='先看项目目录'
    edited=client.patch('/api/startup/breakdowns/'+p['id'],headers=HEADERS,json={'expected_revision':p['revision'],'steps':steps,'minimum_id':steps[0]['id']})
    assert edited.status_code==200,edited.text
    p=edited.json();saved=confirm(client,p,selected=[steps[0]['id']]);assert saved.status_code==200,saved.text
    assert confirm(client,p,selected=[steps[0]['id']]).json()['mapping']==saved.json()['mapping']
    assert confirm(client,p).status_code==409
    assert gen(client,tid).json()['id']==p['id'] and len(provider)==1  # Reopening a saved target reuses the plan.
    start=client.post('/api/startup/breakdowns/'+p['id']+'/start',headers=HEADERS,json={'step_id':steps[0]['id']})
    assert start.status_code==200,start.text
    task_id=start.json()['task_id'];assert client.get(start.json()['href']).status_code==200
    assert client.post('/focus/start',headers=HEADERS,data={'mode':'elapsed','task_id':task_id,'request_id':str(uuid4())}).status_code==200
    with camp['sessions']() as db:
        assert db.get(Task,UUID(task_id)).parent_task_id==tid
        assert db.scalar(select(func.count()).select_from(Task).where(Task.parent_task_id==tid))==1
        assert db.scalar(select(func.count()).select_from(RewardEntry).where(RewardEntry.user_id==camp['user']))==0
    assert len(client.get('/api/startup/breakdowns?task_type=task&task_id='+str(tid)).json()['items'])==1


def test_quest_milestones_and_confirmed_regeneration_duplicate_reuse(ai,provider):
    camp,settings,app,client=ai
    p=gen(client,camp['quest'],'quest').json();saved=confirm(client,p,'milestones')
    assert saved.status_code==200,saved.text
    assert len(saved.json()['mapping'])==2
    next_plan=gen(client,camp['quest'],'quest',saved.json()).json();assert next_plan['id']!=p['id']
    assert confirm(client,next_plan,'milestones').status_code==409
    reuse={s['id']:saved.json()['mapping'][p['advice']['steps'][i]['id']]['id'] for i,s in enumerate(next_plan['advice']['steps'])}
    reused=confirm(client,next_plan,'milestones',reuse=reuse);assert reused.status_code==200,reused.text
    with camp['sessions']() as db:
        assert db.scalar(select(func.count()).select_from(Milestone).where(Milestone.main_quest_id==camp['quest']))==3
        assert db.scalar(select(func.count()).select_from(QuestEvent).where(QuestEvent.main_quest_id==camp['quest']))==2
    step=p['advice']['steps'][0]['id'];start=client.post('/api/startup/breakdowns/'+p['id']+'/start',headers=HEADERS,json={'step_id':step,'create_task':True})
    assert start.status_code==200,start.text
    assert client.post('/api/startup/breakdowns/'+p['id']+'/start',headers=HEADERS,json={'step_id':step,'create_task':True}).json()==start.json()


@pytest.mark.parametrize('mode',['repeat','child'])
def test_restricted_targets_use_checklists_without_rewards(ai,provider,mode):
    camp,settings,app,client=ai
    parent=create(camp,repeat_rule='daily' if mode=='repeat' else 'none')
    tid=parent if mode=='repeat' else create(camp,parent_task_id=str(parent))
    p=gen(client,tid).json();assert p['target']['modes']==['checklist']
    assert confirm(client,p).status_code==409
    saved=confirm(client,p,'checklist');assert saved.status_code==200,saved.text
    payload=dict(step_id=p['advice']['steps'][0]['id'],checked=True,expected_version=0,request_id=str(uuid4()))
    url='/api/startup/breakdowns/'+p['id']+'/checklist'
    checked=client.patch(url,headers=HEADERS,json=payload);assert checked.status_code==200,checked.text
    assert client.patch(url,headers=HEADERS,json=payload).json()['checklist_version']==1
    assert client.patch(url,headers=HEADERS,json=payload|{'request_id':str(uuid4())}).status_code==409
    with camp['sessions']() as db:
        assert db.get(Task,tid).status=='todo'
        assert db.scalar(select(func.count()).select_from(RewardEntry).where(RewardEntry.user_id==camp['user']))==0
    start=client.post('/api/startup/breakdowns/'+p['id']+'/start',headers=HEADERS,json={'step_id':payload['step_id']})
    assert start.json()['task_id']==str(tid)


def test_permissions_stale_state_deleted_target_and_failure(ai,provider,monkeypatch):
    camp,settings,app,client=ai;tid=create(camp)
    p=gen(client,tid).json()
    with camp['sessions']() as db:
        with pytest.raises(AIError):service.get_plan(db,camp['other'],UUID(p['id']))
    assert client.post('/api/startup/states',headers=HEADERS,json=dict(pressure=30,energy=70,confirmed=True,request_id=str(uuid4()),expected_generation=0)).status_code==200
    assert confirm(client,p).status_code==409
    def failure(*a,**kw):raise AIError('upstream_timeout','safe timeout',504)
    monkeypatch.setattr(service.AIService,'generate',failure)
    failed=gen(client,tid,previous=p).json();assert failed['status']=='failed'
    assert client.get('/api/startup/breakdowns/'+p['id']).json()['status']=='draft'
    with camp['sessions'].begin() as db:
        row=db.get(Task,tid);tasks.execute(db,camp['user'],uuid4(),'delete',{},[tid],{str(tid):row.version})
    assert client.get('/api/startup/breakdowns/'+p['id']).status_code==404
    assert gen(client,tid).status_code==404
    assert client.post('/api/startup/breakdowns',json={}).status_code==403


def test_atomic_save_rolls_back_all_steps(ai,provider,monkeypatch):
    camp,settings,app,client=ai;tid=create(camp);p=gen(client,tid).json()
    original=tasks.execute;calls=[]
    def fail_second(*a,**kw):
        calls.append(1)
        if len(calls)==2:raise tasks.TaskError('synthetic rejection',409)
        return original(*a,**kw)
    monkeypatch.setattr(tasks,'execute',fail_second)
    assert confirm(client,p).status_code==409
    with camp['sessions']() as db:
        assert db.scalar(select(func.count()).select_from(Task).where(Task.parent_task_id==tid))==0
        assert db.get(BreakdownPlan,UUID(p['id'])).status=='draft'


def test_edit_during_generation_prevents_late_overwrite(ai,provider,monkeypatch):
    camp,settings,app,client=ai;tid=create(camp);p=gen(client,tid).json()
    entered,release=Event(),Event()
    def slow(*a,**kw):
        assert camp['engine'].pool.checkedout()==0
        entered.set();assert release.wait(30)
        return {'content':Advice(**advice())}
    monkeypatch.setattr(service.AIService,'generate',slow)
    payload=Generate(task_type='task',task_id=tid,request_id=uuid4(),previous_id=p['id'],expected_revision=p['revision'],feedback='再简单些')
    with ThreadPoolExecutor(max_workers=1) as pool:
        result=pool.submit(service.generate,app.state.database,settings,camp['user'],payload)
        try:
            assert entered.wait(20)
            assert service.generate(app.state.database,settings,camp['user'],payload)['status']=='generating'
            steps=p['advice']['steps'];steps[0]['title']='人工修改保留'
            with camp['sessions'].begin() as db:service.edit(db,camp['user'],UUID(p['id']),Edit(expected_revision=p['revision'],steps=steps,minimum_id=steps[0]['id']))
        finally:release.set()
        assert result.result(timeout=30)['status']=='failed'
    assert client.get('/api/startup/breakdowns/'+p['id']).json()['advice']['steps'][0]['title']=='人工修改保留'


def test_breakdown_state_suggestion_requires_explicit_confirmation(ai,provider,monkeypatch):
    camp,settings,app,client=ai;tid=create(camp)
    from test_startup_chat import advice as state_advice
    value=advice()|{'state_advice':state_advice()}
    monkeypatch.setattr(service.AIService,'generate',lambda *a,**kw:{'content':Advice(**value)})
    p=gen(client,tid).json()
    with camp['sessions']() as db:assert db.get(StateCurrent,camp['user']) is None
    saved=client.post('/api/startup/states',headers=HEADERS,json=dict(pressure=60,energy=70,confirmed=True,request_id=str(uuid4()),expected_generation=0,source_plan_id=p['id']))
    assert saved.status_code==200,saved.text
    assert saved.json()['source_plan_id']==p['id']
    assert confirm(client,p).status_code==409
