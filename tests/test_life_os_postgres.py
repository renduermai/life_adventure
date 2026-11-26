import json
import os
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select
from app.core.config import load_settings, postgres_url
from app.modules.ai_gateway.security import AIError
from app.modules.ai_gateway.service import AIService
from app.modules.ai_gateway.models import AIConfig
from app.modules.life_os.schemas import Output
from test_distractions_postgres import notes
from test_tasks_postgres import task_engine

HEADERS={'Origin':'http://testserver'}
BASE='/api/life-os'

def output(mid):
    return Output(reply='先喝水，再整理桌面的一角。',energy={'value':40,'reason':'用户说累'},bandwidth={'value':None,'reason':'信息不足'},order={'value':35,'reason':'桌面乱'},core_conflict='想做事但感到疲惫',triggers=['事情多'],likely_behaviors=['可能暂停行动'],behavior_contribution='短暂休息或有帮助',ideal_solution='逐步建立合适节奏',feasible_action='拿走一个空杯子',life_layers=['生活秩序'],need_layers=['安全'],suggested_mode='yellow',schedule_update_needed=False,attractor_update_needed=False,source_ids=[mid])

def send(client,text='今天事情多有些累，桌面很乱。'):
    payload={'request_id':str(uuid4()),'content':text}
    r=client.post(BASE+'/messages',headers=HEADERS,json=payload);assert r.status_code==200,r.text
    return r.json(),payload

def analyze(client,mid,rid=None):
    return client.post(BASE+'/messages/'+str(mid)+'/analyze',headers=HEADERS,json={'request_id':str(rid or uuid4()),'consent_external':True})

def test_persistence_idempotency_permissions_failure_correction(notes,monkeypatch):
    client,sessions,uid,other,app=notes
    first,payload=send(client)
    assert client.post(BASE+'/messages',headers=HEADERS,json=payload).json()['id']==first['id']
    calls=[]
    def generate(self,user,purpose,messages,request_id,**kw):
        calls.append(messages);return {'content':output(UUID(first['id'])),'model_id':'mock','config_version':1,'usage':None}
    monkeypatch.setattr(AIService,'generate',generate)
    rid=uuid4();result=analyze(client,first['id'],rid);assert result.status_code==200,result.text
    assert analyze(client,first['id'],rid).json()['id']==result.json()['id'] and len(calls)==1
    correction={'request_id':str(uuid4()),'energy':55,'bandwidth':None,'order':45}
    r=client.post(BASE+'/analyses/'+result.json()['id']+'/state',headers=HEADERS,json=correction);assert r.status_code==200,r.text
    assert client.get(BASE+'/messages').json()['state']['result']['energy']['value']==55
    def timeout(*args,**kw):raise AIError('upstream_timeout','timeout',504)
    monkeypatch.setattr(AIService,'generate',timeout)
    assert analyze(client,first['id']).status_code==504
    data=client.get(BASE+'/messages').json();assert data['items'][0]['content']==payload['content'] and data['state']['result']['energy']['value']==55
    assert data['items'][0]['attempt']['error_code']=='upstream_timeout'
    assert len(client.get(BASE+'/messages/'+first['id']+'/analyses').json()['items'])==3
    from app.main import create_app
    from app.core.config import Settings
    from fastapi.testclient import TestClient
    fresh=create_app(Settings(_env_file=None))
    fresh.state.database.sessions=sessions;fresh.state.database.transaction=app.state.database.transaction
    with TestClient(fresh) as reader:
        reader.cookies.set('camp_session',str(uid))
        assert reader.get(BASE+'/messages').json()['state']['result']['energy']['value']==55
    client.cookies.set('camp_session',str(other))
    assert client.get(BASE+'/messages').json()['items']==[]
    assert analyze(client,first['id']).status_code==404
    client.cookies.clear();assert client.get(BASE+'/messages').status_code==401

def test_truncation_sources_and_recent_context(notes,monkeypatch):
    client,_,uid,_,_=notes
    first,_=send(client);mid=first['id']
    def generate(self,user,purpose,messages,request_id,**kw):return {'content':output(UUID(mid)),'model_id':'mock','config_version':1,'usage':None}
    monkeypatch.setattr(AIService,'generate',generate);assert analyze(client,mid).status_code==200
    second,_=send(client,'我已经移走空杯子，感觉轻松一点。')
    def second_call(self,user,purpose,messages,request_id,**kw):
        assert first['id'] in messages[1]['content'];assert '先喝水' in messages[1]['content']
        return {'content':output(uuid4()),'model_id':'mock','config_version':1,'usage':None}
    monkeypatch.setattr(AIService,'generate',second_call)
    assert analyze(client,second['id']).json()['code']=='invalid_sources'
    def truncated(*args,**kwargs):raise AIError('output_truncated','truncated',502)
    monkeypatch.setattr(AIService,'generate',truncated)
    assert analyze(client,mid).json()['code']=='output_truncated'
    assert client.get(BASE+'/messages').json()['state']['message_id']==mid

def test_real_configured_model(notes,monkeypatch):
    if os.getenv('LIFE_OS_LIVE')!='1':pytest.skip('真实模型未显式启用')
    client,sessions,uid,_,app=notes
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    settings=load_settings();engine=create_engine(postgres_url(settings.database_url.get_secret_value()),hide_parameters=True)
    with Session(engine) as db:
        config=db.scalar(select(AIConfig).where(AIConfig.enabled.is_(True),AIConfig.is_default.is_(True),AIConfig.deleted_at.is_(None)))
        assert config is not None
        values={k:getattr(config,k) for k in ('base_url','model_id','protocol','encrypted_key','key_version','key_mask')}
    engine.dispose()
    with sessions.begin() as db:db.add(AIConfig(user_id=uid,create_request_id=uuid4(),create_fingerprint='synthetic',name='synthetic-life-os',is_default=True,**values))
    app.state.settings=settings
    # Restore the actual implementation replaced by the reusable isolation fixture.
    monkeypatch.undo()
    first,_=send(client,'合成测试：今天整理书桌时有点累，只想先移走一个杯子。')
    result=analyze(client,first['id']);assert result.status_code==200,result.text
    data=result.json();assert data['status']=='succeeded'
    from app.modules.life_os.problem_schemas import ProblemOutput
    ProblemOutput.model_validate(data['result'])
    assert first['id'] in data['result']['source_ids']
    assert client.get(BASE+'/messages').json()['state']['id']==data['id']
    print('LIVE_MODEL',data['model_id'],'USAGE',data['usage'])


def test_browser_real_database_chat(notes,monkeypatch):
    import socket,threading,time
    import uvicorn
    from playwright.sync_api import sync_playwright,expect
    client,_,uid,_,app=notes
    def generate(self,user,purpose,messages,request_id,**kw):
        mid=json.loads(messages[1]['content'])['recent_messages'][-1]['id']
        return {'content':output(UUID(mid)),'model_id':'mock','config_version':1,'usage':None}
    monkeypatch.setattr(AIService,'generate',generate)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.context.add_cookies([{'name':'camp_session','value':str(uid),'url':f'http://127.0.0.1:{port}'}])
            page.goto(f'http://127.0.0.1:{port}/life-os')
            page.locator('#life-os-input').fill('今天事情多有些累，桌面很乱。')
            page.locator('#life-os-consent').check();page.locator('#life-os-send').click()
            expect(page.locator('#life-os-feedback')).to_have_text('分析已保存。',timeout=30000)
            expect(page.locator('.life-os-reply')).to_have_text('先喝水，再整理桌面的一角。')
            page.locator('input[name=energy]').fill('60');page.get_by_role('button',name='保存校准').click()
            expect(page.locator('#life-os-feedback')).to_have_text('状态校准已保存。')
            page.reload();expect(page.locator('input[name=energy]')).to_have_value('60')
            page.set_viewport_size({'width':390,'height':844});expect(page.locator('#sidebar')).to_have_css('visibility','hidden')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors
            browser.close()
    finally:server.should_exit=True;thread.join(10)
