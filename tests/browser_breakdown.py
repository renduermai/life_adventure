"""Headless breakdown UI contract test; synthetic API, no database or model calls."""
import copy
import sys
import tempfile
import threading
import time
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright,expect
from app.main import create_app
from app.core.config import Settings


def run():
    server=uvicorn.Server(uvicorn.Config(create_app(Settings(_env_file=None,log_level='ERROR')),host='127.0.0.1',port=8767,access_log=False,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    tid,pid,sid,nonce=map(str,[uuid4(),uuid4(),uuid4(),uuid4()])
    ctx=dict(kind='task',id=tid,title='整理一个测试项目',description='合成验收目标',main_quest='独立副本',progress=0,status='todo',href='/tasks/'+tid,steps=[],modes=['tasks','checklist'],state=None,snapshot_id=None,generation=0,existing=[],recommendation=None)
    plan=None;model_calls=0;requests={};confirmed=None
    def route_api(route):
        nonlocal plan,model_calls,confirmed
        request=route.request;path=request.url.split('8767')[1].split('?')[0];value={}
        if path=='/api/startup/target':value=ctx
        elif path=='/api/startup/current':value={'generation':0,'state':None}
        elif path=='/api/startup/recommendations':value={'items':[],'message':'尚未评估'}
        elif path in ['/api/startup/history','/api/startup/chat/conversations']:value={'items':[],'next_offset':None}
        elif path=='/api/startup/breakdowns' and request.method=='GET':value={'items':[plan] if plan else [],'target':ctx,'next_offset':None}
        elif path=='/api/startup/breakdowns' and request.method=='POST':
            data=request.post_data_json
            if data['request_id'] not in requests:
                model_calls+=1
                plan=dict(id=pid,previous_id=None,status='draft',revision=1,stale=False,target=ctx,feedback='',created_at='2026-11-15T08:00:00+08:00',save_mode=None,mapping={},execution={},checklist={},checklist_version=0,advice=dict(reply='先打开文件夹就好。',minimum_id=sid,state_advice=None,steps=[dict(id=sid,title='打开项目目录',detail='只看目录',minutes=2,done_when='看到文件列表')]))
                requests[data['request_id']]=True
            value=plan
        elif path=='/api/startup/breakdowns/'+pid and request.method=='PATCH':
            data=request.post_data_json;plan['advice']['steps']=data['steps'];plan['advice']['minimum_id']=data['minimum_id'];plan['revision']+=1;value=plan
        elif path=='/api/startup/breakdowns/'+pid+'/confirm':
            data=request.post_data_json
            if not data['allow_duplicates']:
                route.fulfill(status=409,json={'error':'发现相似内容，请复用或明确允许重复。'});return
            confirmed=copy.deepcopy(data);plan['status']='confirmed';plan['revision']+=1;plan['mapping']={sid:{'kind':'task','id':str(uuid4()),'reused':False}};plan['save_mode']='tasks';value=plan
        elif path=='/api/startup/breakdowns/'+pid+'/start':value={'href':'/focus?task='+plan['mapping'][sid]['id'],'task_id':plan['mapping'][sid]['id']}
        elif path=='/api/startup/breakdowns/'+pid:value=plan
        else:raise AssertionError(path)
        route.fulfill(json=value)
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000},reduced_motion='reduce');errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.route('**/api/startup/**',route_api)
            page.route('**/focus?**',lambda route:route.fulfill(body='<html><h1>原有专注入口</h1></html>',content_type='text/html'))
            url='http://127.0.0.1:8767/startup?task_type=task&task_id='+tid+'&generate='+nonce+'#chat'
            page.goto(url);expect(page.locator('#breakdown-confirm')).to_be_visible()
            assert model_calls==1 and confirmed is None
            expect(page.locator('#state-chat-content')).to_be_hidden()
            page.locator('[data-field="title"]').fill('先看一眼项目目录')
            expect(page.locator('#breakdown-confirm')).to_be_disabled()
            page.locator('#breakdown-edit').click();expect(page.locator('#breakdown-confirm')).to_be_enabled()
            page.locator('#breakdown-confirm').click();expect(page.locator('#breakdown-message')).to_contain_text('相似内容')
            page.locator('#breakdown-duplicates').check();page.locator('#breakdown-confirm').click()
            expect(page.locator('#breakdown-start')).to_be_visible();assert confirmed
            assert 'generate=' not in page.url
            page.reload();expect(page.locator('#breakdown-start')).to_be_visible();assert model_calls==1
            out=Path(tempfile.gettempdir())/'adventure-step8-verification';out.mkdir(exist_ok=True)
            page.evaluate('scrollTo(0,0)');page.screenshot(path=str(out/'desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844});page.evaluate('scrollTo(0,0)')
            expect(page.locator('#sidebar')).to_be_hidden();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(out/'mobile.png'),full_page=True)
            page.locator('#breakdown-start').click();expect(page).to_have_url(__import__('re').compile('/focus\?task='))
            assert not errors,errors
            browser.close()
            print('PASS: navigation generation, manual edit, confirmation, duplicate warning, reload no new generation, focus link, 390px; synthetic HTTP.')
    finally:server.should_exit=True;thread.join(timeout=10)


if __name__=='__main__':run()
