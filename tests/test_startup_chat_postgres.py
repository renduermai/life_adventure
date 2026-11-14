from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select
from app.modules.startup_chat import service
from app.modules.startup_chat.models import ChatTurn
from app.modules.startup_chat.schemas import MessageInput, StateAdvice
from app.modules.startup_state.models import StateCurrent, StateSnapshot
from app.modules.ai_gateway.security import AIError
from app.modules.quests.models import MainQuest
from test_ai_postgres import ai, make, task_engine, camp
from test_startup_chat import advice

pytestmark=pytest.mark.integration
HEADERS={'Origin':'http://testserver'}


def send(client, message='精力还行但事情太多', cid=None, version=0, **extra):
    return client.post('/api/startup/chat/messages', json=dict(message=message,conversation_id=cid,expected_version=version,request_id=str(uuid4()))|extra, headers=HEADERS)


def save(client, turn=None, generation=0, **extra):
    return client.post('/api/startup/states', json=dict(pressure=65,energy=70,difficulty='我修改了困难',confirmed=True,request_id=str(uuid4()),expected_generation=generation,source_turn_id=turn)|extra, headers=HEADERS)


def test_chat_confirmation_history_and_shared_refresh(ai, monkeypatch):
    camp,settings,app,client=ai
    make(ai)
    seen=[]
    def provider(self,uid,purpose,messages,request_id,output_schema=None,**kw):
        assert camp['engine'].pool.checkedout()==0
        seen.append(messages)
        return {'content':StateAdvice(**advice(ready=len(seen)>1,pressure=70 if len(seen)>1 else None))}
    monkeypatch.setattr(service.AIService,'generate',provider)
    first=send(client).json();assert first['status']=='succeeded' and not first['response']['ready']
    assert save(client,first['id']).status_code==409
    second=send(client,'压力偏高，想先理清一件事',first['conversation_id'],1).json()
    assert seen[1][1]['content']=='精力还行但事情太多'
    with camp['sessions']() as db: assert db.get(StateCurrent,camp['user']) is None
    confirmed=save(client,second['id']);assert confirmed.status_code==200,confirmed.text
    snapshot=confirmed.json()
    assert snapshot['pressure']==65 and snapshot['source_turn_id']==second['id']
    refreshed=client.post('/api/startup/refresh',json={'request_id':str(uuid4()),'expected_snapshot_id':snapshot['snapshot_id']},headers=HEADERS)
    assert refreshed.status_code==200,refreshed.text
    assert len(seen)==2  # Empty-description quest needs no model; refresh cannot invoke state chat.
    batch=refreshed.json()
    assert client.get('/api/startup/recommendations').json()['batch_id']==batch['batch_id']
    assert client.get(f"/api/startup/target?task_type=quest&task_id={camp['quest']}").json()['batch_id']==batch['batch_id']
    assert client.get('/api/startup/history').json()['items'][0]['snapshot_id']==snapshot['snapshot_id']
    assert len(client.get('/api/startup/chat/conversations/'+first['conversation_id']).json()['items'])==2
    with camp['sessions']() as db:
        assert db.get(MainQuest,camp['quest']).status=='active'
        assert db.get(StateSnapshot,UUID(snapshot['snapshot_id'])).source_turn_id==UUID(second['id'])


def test_retries_permissions_and_stale_suggestions(ai,monkeypatch):
    camp,settings,app,client=ai
    calls=[]
    monkeypatch.setattr(service.AIService,'generate',lambda *a,**kw:(calls.append(1) or {'content':StateAdvice(**advice())}))
    request_id=str(uuid4())
    first=send(client,request_id=request_id).json()
    assert send(client,request_id=request_id).json()['id']==first['id'] and len(calls)==1
    assert send(client,'changed',request_id=request_id).status_code==409
    assert send(client,cid=first['conversation_id'],version=0).status_code==409
    assert send(client,cid=str(uuid4()),version=1).status_code==404
    with pytest.raises(AIError):
        with camp['sessions']() as db: service.conversation(db,camp['other'],UUID(first['conversation_id']))
    second=send(client,'再聊一条',first['conversation_id'],1).json()
    assert save(client,first['id']).status_code==409  # Older turn cannot be confirmed.
    saved=save(client).json()
    assert save(client,second['id'],generation=1).status_code==409  # State changed during chat.
    assert client.post('/api/startup/refresh',json={'request_id':str(uuid4()),'expected_snapshot_id':str(uuid4())},headers=HEADERS).status_code==409
    history=client.get('/api/startup/history').json()['items'];assert len(history)==1
    assert history[0]['snapshot_id']==saved['snapshot_id']
    assert client.post('/api/startup/chat/messages',json={}).status_code==403
    client.cookies.clear()
    assert client.get('/api/startup/chat/conversations').status_code==401


def test_failed_and_malformed_reply_preserves_message_without_state(ai,monkeypatch):
    camp,settings,app,client=ai
    def failure(*a,**kw): raise AIError('upstream_timeout','safe timeout',504)
    monkeypatch.setattr(service.AIService,'generate',failure)
    first=send(client).json();assert first['status']=='failed' and first['error_code']=='upstream_timeout'
    monkeypatch.setattr(service.AIService,'generate',lambda *a,**kw:{'content':{'ready':True,'pressure':999}})
    second=send(client,cid=first['conversation_id'],version=1).json();assert second['status']=='failed'
    with camp['sessions']() as db:
        assert db.get(StateCurrent,camp['user']) is None
        assert len(list(db.scalars(select(ChatTurn).where(ChatTurn.user_id==camp['user']))))==2


def test_concurrent_send_and_state_change_cannot_overwrite(ai,monkeypatch):
    camp,settings,app,client=ai
    monkeypatch.setattr(service.AIService,'generate',lambda *a,**kw:{'content':StateAdvice(**advice())})
    first=send(client).json()
    entered,release=Event(),Event()
    def provider(*a,**kw):
        entered.set();assert release.wait(30)
        return {'content':StateAdvice(**advice())}
    monkeypatch.setattr(service.AIService,'generate',provider)
    payload=MessageInput(request_id=uuid4(),conversation_id=first['conversation_id'],expected_version=1,message='第二条')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(service.send,app.state.database,settings,camp['user'],payload)
        try:
            assert entered.wait(20)
            assert service.send(app.state.database,settings,camp['user'],payload)['status']=='pending'
            assert send(client,cid=first['conversation_id'],version=2).status_code==409
            assert save(client).status_code==200
        finally: release.set()
        reply=future.result(timeout=30)
    assert save(client,str(reply['id']),generation=1).status_code==409
    assert client.get('/api/startup/current').json()['pressure']==65


def test_paginated_history(ai,monkeypatch):
    camp,settings,app,client=ai
    monkeypatch.setattr(service.AIService,'generate',lambda *a,**kw:{'content':StateAdvice(**advice())})
    first=send(client).json()
    # Seed an archive directly; don't spend model calls testing pagination.
    with camp['sessions'].begin() as db:
        chat=service.conversation(db,camp['user'],UUID(first['conversation_id']));chat.version=23
        for n in range(2,24): db.add(ChatTurn(user_id=camp['user'],conversation_id=chat.id,request_id=uuid4(),fingerprint='x'*64,sequence=n,base_generation=0,message='历史',response=advice(),status='succeeded'))
    url='/api/startup/chat/conversations/'+first['conversation_id']
    page=client.get(url).json();assert len(page['items'])==20 and page['next_before']==4
    older=client.get(url+'?before=4').json();assert [t['sequence'] for t in older['items']]==[1,2,3]
    assert older['next_before'] is None
