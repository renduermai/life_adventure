import socket,threading,time
from datetime import datetime,timezone,date,timedelta
from uuid import uuid4
import pytest,uvicorn
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from alembic import command
from alembic.config import Config
from playwright.sync_api import sync_playwright
from app.core.config import ROOT
from app.modules.shining_memories.people import service as people
from test_distractions_postgres import notes,task_engine

pytestmark=pytest.mark.integration
BASE='/api/shining-memories/items'
H={'Origin':'http://testserver'}

def test_expiry_persistence_migration_dates_and_browser(notes,task_engine,monkeypatch):
    client,sessions,uid,other,app=notes
    data=dict(request_id=str(uuid4()),name='合成健身权益',purchase_date='2026-01-01',purchase_price='120',category='健身')
    original=client.post(BASE,headers=H,json=data);assert original.status_code==200
    iid=original.json()['id']
    # Simulate a pre-upgrade item in the isolated schema, then verify backfill.
    with task_engine.begin() as conn:
        cfg=Config(str(ROOT/'alembic.ini'));cfg.attributes['connection']=conn
        command.downgrade(cfg,'0026_memory_wishes');command.upgrade(cfg,'head');command.check(cfg)
    row=client.get(BASE+'/'+iid).json();assert row['is_entitlement'] is False and row['expires_at'] is None and row['name']==data['name']
    assert client.post(BASE,headers=H,json=data).json()['id']==iid
    fields={k:v for k,v in data.items() if k!='request_id'}
    assert client.patch(BASE+'/'+iid,headers=H,json=fields|{'expected_version':1,'is_entitlement':True}).status_code==422
    assert client.patch(BASE+'/'+iid,headers=H,json=fields|{'expected_version':1,'is_entitlement':True,'expires_at':'2025-12-31'}).status_code==422
    monkeypatch.setattr(people,'now',lambda:datetime(2026,11,23,0,30,tzinfo=timezone.utc))
    expiry='2026-11-23'
    r=client.patch(BASE+'/'+iid,headers=H,json=fields|{'expected_version':1,'is_entitlement':True,'expires_at':expiry});assert r.status_code==200,r.text
    assert r.json()['remaining_days']==0
    baseline=r.json()['daily_cost']
    for delta in (-2,0,3):
        expires=str(date(2026,11,23)+timedelta(days=delta))
        result=client.patch(BASE+'/'+iid,headers=H,json=fields|{'expected_version':client.get(BASE+'/'+iid).json()['version'],'is_entitlement':True,'expires_at':expires})
        assert result.json()['remaining_days']==delta and result.json()['daily_cost']==baseline
    from app.modules.identity.models import User
    with sessions.begin() as db:db.get(User,uid).timezone='America/Los_Angeles'
    assert client.get(BASE).json()['today']=='2026-11-22'
    assert client.get(BASE+'/'+iid).json()['remaining_days']==4
    with sessions.begin() as db:db.get(User,uid).timezone='Asia/Shanghai'
    with task_engine.connect() as conn:
        with pytest.raises(IntegrityError):
            with conn.begin():conn.execute(text('UPDATE memory_items SET expires_at=NULL WHERE id=:id'),{'id':iid})
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False));thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        assert server.started
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True);page=browser.new_page(viewport={'width':390,'height':844});errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.context.add_cookies([{'name':'camp_session','value':str(uid),'url':f'http://127.0.0.1:{port}'}])
            page.goto(f'http://127.0.0.1:{port}/shining-memories/items')
            page.locator('.item-expiry').get_by_text('距离到期还有 3 天',exact=True).wait_for()
            page.get_by_role('button',name='＋ 添加物品').click()
            assert page.locator('[name=purchase_date]').input_value()=='2026-11-23'
            assert not page.locator('[name=is_entitlement]').is_checked()
            page.locator('[name=is_entitlement]').check();assert page.locator('[name=expires_at]').is_visible()
            assert page.locator('[name=expires_at]').evaluate('e=>e.required')
            page.locator('[name=is_entitlement]').uncheck()
            page.get_by_role('button',name='取消',exact=True).click()
            page.get_by_role('button',name='编辑 合成健身权益').click()
            page.locator('[name=is_entitlement]').uncheck()
            page.once('dialog',lambda d:d.dismiss());page.get_by_role('button',name='保存物品',exact=True).click()
            assert client.get(BASE+'/'+iid).json()['is_entitlement']
            page.once('dialog',lambda d:d.accept());page.get_by_role('button',name='保存物品',exact=True).click()
            page.get_by_text('物品已保存。',exact=True).wait_for()
            saved=client.get(BASE+'/'+iid).json();assert saved['expires_at'] is None and not saved['is_entitlement']
            page.reload();page.get_by_role('button',name='编辑 合成健身权益').wait_for()
            assert page.locator('.item-expiry').count()==0
            for width in (320,390,1366):
                page.set_viewport_size({'width':width,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors,errors
            browser.close()
    finally:server.should_exit=True;thread.join(10);sock.close()
