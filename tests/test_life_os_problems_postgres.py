import json,os
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func
from app.modules.life_os.problem_schemas import ProblemOutput
from app.modules.life_os.problem_models import Problem,LifeEvent,Experience,EventSource,EventProblem
from app.modules.ai_gateway.service import AIService
from app.modules.distractions.models import DistractionNote
from test_distractions_postgres import notes
from test_tasks_postgres import task_engine
from test_life_os_postgres import output,send,analyze,BASE,HEADERS


def make_output(mid,content,ctx,relation='new',name='环境混乱',action='',feedback='',outcome='unknown'):
    event=ctx['events'][0]['id'] if relation=='continue' else None
    problem=next((p['id'] for p in ctx['problems'] if p['name']==name),None)
    return ProblemOutput(**output(UUID(mid)).model_dump(),event={'relation':relation,'existing_event_id':event,'title':'桌面整理事件','evidence_quote':content[:100],'action_quote':action,'feedback_quote':feedback,'outcome':outcome,'problems':[{'existing_id':problem,'name':name,'mechanism':'先整理一个角落','observation':'AI 提议尝试较小动作，效果待验证'}]})

def install(monkeypatch,relation='new',name='环境混乱',action='',feedback='',outcome='unknown'):
    def generate(self,user,purpose,messages,request_id,**kw):
        data=json.loads(messages[1]['content']);m=data['recent_messages'][-1]
        return {'content':make_output(m['id'],m['content'],data['problem_context'],relation,name,action,feedback,outcome),'model_id':'mock','config_version':1,'usage':None}
    monkeypatch.setattr(AIService,'generate',generate)

def chat(client,text):
    m,_=send(client,text);r=analyze(client,m['id']);assert r.status_code==200,r.text
    return m,r.json()

def problems(client):return client.get(BASE+'/problems').json()['items']
def events(client):return client.get(BASE+'/events').json()['items']

def test_distinct_occurrences_not_turns_or_reruns(notes,monkeypatch):
    c,s,uid,_,_=notes;install(monkeypatch)
    first,r=chat(c,'今天桌面很乱。');assert r['experience_status']=='succeeded'
    install(monkeypatch,relation='continue')
    for _ in range(4):chat(c,'继续说刚才同一次整理桌面的事，还没采取行动。')
    assert problems(c)[0]['count']==1 and len(events(c))==1
    assert analyze(c,first['id']).json()['experience_status']=='already_linked'
    assert problems(c)[0]['count']==1
    install(monkeypatch)
    chat(c,'过了一周，桌面又重新变乱，这是另一次事件。')
    assert problems(c)[0]['count']==2
    install(monkeypatch,relation='uncertain')
    chat(c,'我不确定这是不是之前那件事。')
    assert problems(c)[0]['count']==2
    assert sum(e['status']=='pending' for e in events(c))==1
    pending=next(e for e in events(c) if e['status']=='pending')
    r=c.post(BASE+'/events/'+pending['id']+'/edit',headers=HEADERS,json={'request_id':str(uuid4()),'expected_version':pending['version'],'title':pending['title'],'occurred_at':pending['occurred_at'],'status':'confirmed','problem_ids':pending['problem_ids']})
    assert r.status_code==200,r.text
    assert problems(c)[0]['count']==3

def test_manual_protection_merge_reassign_delete_and_permissions(notes,monkeypatch):
    c,s,uid,other,_=notes;install(monkeypatch);chat(c,'今天桌面很乱。');p=problems(c)[0]
    payload={'request_id':str(uuid4()),'expected_version':p['version'],'name':p['name'],'mechanism':'我自己的处理方式','notes':'用户手填经验'}
    r=c.post(BASE+'/problems/'+p['id']+'/edit',headers=HEADERS,json=payload);assert r.status_code==200,r.text
    assert c.post(BASE+'/problems/'+p['id']+'/edit',headers=HEADERS,json=payload).status_code==200
    install(monkeypatch,relation='continue',name='工作压力');chat(c,'同一个事件也涉及工作压力。')
    old=next(x for x in problems(c) if x['id']==p['id']);assert old['mechanism']=='我自己的处理方式'
    install(monkeypatch,relation='continue');chat(c,'还是这一次桌面整理事件。')
    old=next(x for x in problems(c) if x['id']==p['id']);assert old['mechanism']=='我自己的处理方式'
    source=next(x for x in problems(c) if x['id']!=p['id'])
    r=c.post(BASE+'/problems/'+source['id']+'/merge',headers=HEADERS,json={'request_id':str(uuid4()),'expected_version':source['version'],'target_id':p['id'],'target_version':old['version']});assert r.status_code==200,r.text
    assert len(problems(c))==1 and problems(c)[0]['count']==1
    detail=c.get(BASE+'/problems/'+p['id']).json();e=detail['events'][0];src=e['sources'][0]
    r=c.post(BASE+'/sources/move',headers=HEADERS,json={'request_id':str(uuid4()),'source_id':src['id'],'expected_event_id':e['id'],'expected_version':e['version'],'target_event_id':None,'title':'修正为另一次独立事件'});assert r.status_code==200,r.text
    assert problems(c)[0]['count']==2
    c.cookies.set('camp_session',str(other))
    assert c.get(BASE+'/problems/'+p['id']).status_code==404
    assert c.post(BASE+'/events/'+e['id']+'/feedback',headers=HEADERS,json={'request_id':str(uuid4()),'action':'整理','feedback':'舒服','outcome':'helpful'}).status_code==404
    c.cookies.set('camp_session',str(uid));p=problems(c)[0]
    assert c.post(BASE+'/problems/'+p['id']+'/delete',headers=HEADERS,json={'request_id':str(uuid4()),'expected_version':p['version']}).status_code==200
    assert problems(c)==[]
    with s() as db:assert db.get(Problem,UUID(p['id'])).deleted_at is not None

def test_reported_effects_and_independent_sync_failure(notes,monkeypatch):
    c,s,uid,_,_=notes;install(monkeypatch);m,r=chat(c,'今天桌面很乱。');e=events(c)[0]
    assert e['effect_pending'] and not any(x['kind']=='action' for x in e['experiences'])
    install(monkeypatch,relation='continue',action='我移走了杯子',feedback='感觉轻松了',outcome='helpful')
    chat(c,'我移走了杯子，感觉轻松了。')
    e=events(c)[0];assert not e['effect_pending'];assert problems(c)[0]['count']==1
    assert any(x['kind']=='feedback' and x['outcome']=='helpful' and x['source_quote']=='感觉轻松了' for x in e['experiences'])
    install(monkeypatch,relation='continue',action='凭空捏造的实际行动')
    _,r=chat(c,'我只是想了一下，还没开始。')
    assert r['status']=='succeeded' and r['experience_status']=='failed' and r['experience_error']=='invalid_evidence'
    assert problems(c)[0]['count']==1
    payload={'request_id':str(uuid4()),'action':'手动记录：移走杯子','feedback':'舒服一些','outcome':'helpful'}
    path=BASE+'/events/'+e['id']+'/feedback'
    assert c.post(path,headers=HEADERS,json=payload).status_code==200
    before=len(events(c)[0]['experiences']);assert c.post(path,headers=HEADERS,json=payload).status_code==200
    assert len(events(c)[0]['experiences'])==before

def test_notes_readonly_scope_dedup_and_deleted_source(notes,monkeypatch):
    c,s,uid,other,_=notes;install(monkeypatch);chat(c,'今天桌面乱。');p=problems(c)[0];eid=events(c)[0]['id']
    nr=c.post('/api/distractions/notes',headers=HEADERS,json={'request_id':str(uuid4()),'content':'合成历史记录：一周前整理过一次房间。'}).json()
    assert any(x['id']==nr['id'] for x in c.get(BASE+'/notes?q=合成历史').json()['items'])
    with s() as db:n=db.get(DistractionNote,UUID(nr['id']));before=(n.content,n.version,n.updated_at)
    payload={'request_id':str(uuid4()),'note_id':nr['id'],'event_id':None,'title':'历史房间整理','problem_ids':[p['id']]}
    r=c.post(BASE+'/notes/import',headers=HEADERS,json=payload);assert r.status_code==200,r.text
    assert c.post(BASE+'/notes/import',headers=HEADERS,json=payload).status_code==200
    assert problems(c)[0]['count']==2
    with s() as db:n=db.get(DistractionNote,UUID(nr['id']));assert (n.content,n.version,n.updated_at)==before
    # Deleting the original removes its original text and count from note-only events.
    c.request('DELETE','/api/distractions/notes/'+nr['id'],headers=HEADERS,json={'expected_version':1})
    assert problems(c)[0]['count']==1
    c.cookies.set('camp_session',str(other));assert c.get(BASE+'/notes').json()['items']==[]
    assert c.post(BASE+'/notes/import',headers=HEADERS,json=payload|{'request_id':str(uuid4())}).status_code==404


def test_real_two_turn_event_and_feedback(notes,monkeypatch):
    if os.getenv('LIFE_OS_LIVE')!='1':pytest.skip('真实模型未显式启用')
    c,s,uid,_,app=notes
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import load_settings,postgres_url
    from app.modules.ai_gateway.models import AIConfig
    settings=load_settings();engine=create_engine(postgres_url(settings.database_url.get_secret_value()),hide_parameters=True)
    with Session(engine) as db:
        config=db.scalar(select(AIConfig).where(AIConfig.enabled.is_(True),AIConfig.is_default.is_(True),AIConfig.deleted_at.is_(None)))
        assert config
        values={k:getattr(config,k) for k in ('base_url','model_id','protocol','encrypted_key','key_version','key_mask')}
    engine.dispose()
    with s.begin() as db:db.add(AIConfig(user_id=uid,create_request_id=uuid4(),create_fingerprint='synthetic',name='synthetic-problem-test',is_default=True,**values))
    app.state.settings=settings;monkeypatch.undo()
    _,first=chat(c,'合成测试情境：今天早上我看到书桌上堆满了空杯子和纸，觉得很烦。刚发生这件事，还没有采取任何行动。')
    assert first['experience_status']=='succeeded',first['experience_error']
    first_events=events(c);assert len(first_events)==1
    _,second=chat(c,'继续刚才同一次书桌很乱的事件，并非新事件：我已经把空杯子拿到厨房了，现在感觉舒服一些。')
    assert second['experience_status']=='succeeded'
    assert len(events(c))==1
    e=events(c)[0];assert len(e['sources'])==2
    assert any(x['kind']=='action' for x in e['experiences'])
    assert any(x['kind']=='feedback' for x in e['experiences'])
    assert all(p['count']==1 for p in problems(c))
    print('LIVE_MODEL',first['model_id'],'USAGE1',first['usage'],'USAGE2',second['usage'])


def test_note_selection_scope_is_not_implicitly_carried_forward(notes,monkeypatch):
    c,s,uid,_,_=notes
    note=c.post('/api/distractions/notes',headers=HEADERS,json={'request_id':str(uuid4()),'content':'合成授权背景：喜欢用音乐辅助整理。'}).json()
    seen=[]
    def generate(self,user,purpose,messages,request_id,**kw):
        data=json.loads(messages[1]['content']);seen.append(data)
        m=data['recent_messages'][-1]
        return {'content':make_output(m['id'],m['content'],data['problem_context'],'continue' if data['problem_context']['events'] else 'new'),'model_id':'mock','config_version':1,'usage':None}
    monkeypatch.setattr(AIService,'generate',generate)
    m,_=send(c,'今天桌面很乱。')
    r=c.post(BASE+'/messages/'+m['id']+'/analyze',headers=HEADERS,json={'request_id':str(uuid4()),'consent_external':True,'note_ids':[note['id']]})
    assert r.status_code==200 and r.json()['experience_status']=='succeeded',r.text
    assert seen[0]['problem_context']['selected_notes'][0]['id']==note['id']
    second,_=chat(c,'继续刚才同一件事，但本轮不要读取杂念。')
    assert seen[1]['problem_context']['selected_notes']==[]
    assert seen[1]['previous_state'] is None
    previous=next(x for x in seen[1]['recent_messages'] if x['id']==m['id'])
    assert previous['reply'] is None
    # A different user cannot authorize someone else's note.
    assert len(json.dumps(seen[1]['problem_context'],ensure_ascii=False))<=7000


def test_schema_partial_and_source_change_preserve_core_or_old_state(notes,monkeypatch):
    c,s,uid,_,_=notes
    def invalid_event(self,user,purpose,messages,request_id,**kw):
        data=json.loads(messages[1]['content']);mid=UUID(data['recent_messages'][-1]['id'])
        return {'content':ProblemOutput(**output(mid).model_dump(),event={'unexpected':'malformed event'}),'model_id':'mock','config_version':1,'usage':None}
    monkeypatch.setattr(AIService,'generate',invalid_event)
    _,r=chat(c,'今天桌面很乱。')
    assert r['status']=='succeeded' and r['experience_status']=='failed' and r['experience_error']=='invalid_schema'
    assert problems(c)==[]
    note=c.post('/api/distractions/notes',headers=HEADERS,json={'request_id':str(uuid4()),'content':'合成背景'}).json()
    def deleted_source(self,user,purpose,messages,request_id,**kw):
        from datetime import datetime,timezone
        with s.begin() as db:db.get(DistractionNote,UUID(note['id'])).deleted_at=datetime.now(timezone.utc)
        return invalid_event(self,user,purpose,messages,request_id,**kw)
    monkeypatch.setattr(AIService,'generate',deleted_source)
    m,_=send(c,'再次讨论这件事情。')
    r=c.post(BASE+'/messages/'+m['id']+'/analyze',headers=HEADERS,json={'request_id':str(uuid4()),'consent_external':True,'note_ids':[note['id']]})
    assert r.status_code==409 and r.json()['code']=='source_changed'
    history=c.get(BASE+'/messages').json();assert history['items'][0]['attempt']['status']=='failed'
    assert history['state']['result']['reply']=='先喝水，再整理桌面的一角。'
