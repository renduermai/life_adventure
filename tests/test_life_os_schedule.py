import json
import os
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.core.config import load_settings, postgres_url
from app.modules.ai_gateway.service import AIService
from app.modules.ai_gateway.security import AIError
from app.modules.ai_gateway.models import AIConfig
from app.modules.life_os import schedule
from app.modules.life_os.schedule import ScheduleOutput, overlay
from test_distractions_postgres import notes
from test_tasks_postgres import task_engine

H={'Origin':'http://testserver'}

def test_protected_overlay_and_coordination():
    c={'minute':720,'weekday':2,'local_now':'2026-11-27T12:00:00+08:00','identity':{'date':'2026-11-27'},'scene':{'daily_slots':[{'start':'08:00','activity':'past','fixed':False},{'start':'14:00','activity':'appointment','fixed':True},{'start':'18:00','activity':'project','fixed':False}], 'weekly_rhythm':[{'weekday':1,'period':'evening','activity':'past-week','fixed':False},{'weekday':2,'period':'evening','activity':'intense','fixed':False}]}}
    out=ScheduleOutput(reason='reduce load',today_summary='light evening',daily=[{'index':0,'activity':'bad'},{'index':1,'activity':'bad'},{'index':2,'activity':'rest'}],weekly=[{'index':0,'activity':'bad'},{'index':1,'activity':'intense'}])
    result=overlay(c,out)
    assert [x['activity'] for x in result['daily']]==['past','appointment','rest']
    assert result['weekly'][0]['activity']=='past-week'
    assert result['weekly'][1]['activity']=='rest'
    assert c['scene']['daily_slots'][2]['activity']=='project'

def seed(client):
    r=client.post('/api/life-os/scenes',headers=H,json={'name':'合成日程场景','daily_slots':[{'start':'23:50','end':'23:59','activity':'项目学习','fixed':False}],'weekly_rhythm':[{'weekday':6,'period':'evening','activity':'整理房间','fixed':True}]});assert r.status_code==200,r.text
    assert client.post('/api/life-os/mode',headers=H,json={'mode':'red'}).status_code==200
    return r.json()

def test_schedule_persistence_cache_failure_permissions(notes,monkeypatch):
    c,s,uid,other,app=notes;scene=seed(c);calls=[]
    def model(*args,**kw):
        calls.append(1);return {'content':ScheduleOutput(reason='降低负荷',today_summary='保留必要事务',daily=[{'index':0,'activity':'轻量休息'}],weekly=[]),'usage':{'completion_tokens':50}}
    monkeypatch.setattr(AIService,'generate',model)
    url='/api/life-os/schedule/generate'
    assert c.post(url,headers=H,json={'consent_external':False}).status_code==422
    first=c.post(url,headers=H,json={'consent_external':True});assert first.status_code==200,first.text
    assert c.post(url,headers=H,json={'consent_external':True}).json()['cached'] and len(calls)==1
    assert c.get('/api/life-os/schedule').json()['current']['id']==first.json()['id']
    assert c.get('/api/life-os/scenes').json()['items'][0]['daily_slots']==scene['daily_slots']
    c.post('/api/life-os/mode',headers=H,json={'mode':'blue'})
    def fail(*args,**kw):raise AIError('output_truncated','合成截断',502)
    monkeypatch.setattr(AIService,'generate',fail)
    assert c.post(url,headers=H,json={'consent_external':True}).status_code==502
    data=c.get('/api/life-os/schedule').json();assert data['current']['id']==first.json()['id'] and data['attempt']['error_code']=='output_truncated' and data['stale']
    c.cookies.set('camp_session',str(other));assert c.get('/api/life-os/schedule').json()['current'] is None
    c.cookies.clear();assert c.get('/api/life-os/schedule').status_code==401

def test_schedule_browser_auto_mode_change(notes,monkeypatch):
    import socket,threading,time
    import uvicorn
    from playwright.sync_api import sync_playwright,expect
    c,_,uid,_,app=notes;seed(c);calls=[]
    def model(*args,**kw):
        calls.append(1);return {'content':ScheduleOutput(reason='合成建议原因',today_summary='适量恢复',daily=[],weekly=[]),'usage':None}
    monkeypatch.setattr(AIService,'generate',model)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False));thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True);page=browser.new_page(viewport={'width':1366,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.context.add_cookies([{'name':'camp_session','value':str(uid),'url':f'http://127.0.0.1:{port}'}]);page.goto(f'http://127.0.0.1:{port}/life-os')
            page.locator('#life-schedule-consent').check();page.locator('#life-schedule-generate').click()
            expect(page.locator('#life-schedule-daily')).to_contain_text('合成建议原因',timeout=30000)
            expect(page.locator('#life-schedule-weekly')).to_contain_text('整理房间')
            with page.expect_response(lambda r:'/schedule/generate' in r.url and r.request.method=='POST',timeout=30000) as updated:
                page.locator('#life-mode-list button[data-mode="blue"]').click()
            assert updated.value.status==200
            assert len(calls)==2
            expect(page.locator('#life-schedule-feedback')).to_have_text('每日与每周建议已一起保存。',timeout=30000)
            page.reload();expect(page.locator('#life-schedule-daily')).to_contain_text('合成建议原因',timeout=30000)
            page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors,errors
            browser.close()
    finally:server.should_exit=True;thread.join(10)

def test_live_schedule(notes,monkeypatch):
    if os.getenv('LIFE_OS_LIVE')!='1':pytest.skip('真实模型未显式启用')
    c,s,uid,_,app=notes;seed(c);settings=load_settings()
    engine=create_engine(postgres_url(settings.database_url.get_secret_value()),hide_parameters=True)
    with Session(engine) as db:
        config=db.scalar(select(AIConfig).where(AIConfig.enabled.is_(True),AIConfig.is_default.is_(True),AIConfig.deleted_at.is_(None)))
        assert config
        values={k:getattr(config,k) for k in ('base_url','model_id','protocol','encrypted_key','key_version','key_mask')}
    engine.dispose()
    with s.begin() as db:db.add(AIConfig(user_id=uid,create_request_id=uuid4(),create_fingerprint='synthetic',name='schedule-synthetic',is_default=True,**values))
    app.state.settings=settings;monkeypatch.undo()
    r=c.post('/api/life-os/schedule/generate',headers=H,json={'consent_external':True});assert r.status_code==200,r.text
    result=r.json();assert result['status']=='succeeded' and result['result']['daily'] and result['result']['weekly']
    assert c.get('/api/life-os/schedule').json()['current']['id']==result['id']
    print('LIVE_SCHEDULE_USAGE',result['usage'])
