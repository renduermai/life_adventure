import socket
import threading
import time
from uuid import uuid4
import pytest
import uvicorn
from playwright.sync_api import sync_playwright
from app.core.config import Settings
from app.modules.ai_gateway.models import AIConfig
from test_distractions_postgres import notes,task_engine

pytestmark=pytest.mark.integration


def test_display_authentication_and_existing_models_browser(notes):
    client,sessions,uid,other,app=notes
    private='sb_secret_SYNTHETIC_PRIVATE_BROWSER'
    public='sb_publishable_SYNTHETIC_PUBLIC_BROWSER'
    project='https://'+'a'*20+'.supabase.co'
    app.state.settings=Settings(_env_file=None,supabase_url=project,supabase_publishable_key=public,
        supabase_service_role_key=private,supabase_storage_bucket='synthetic-bucket')
    with sessions.begin() as db:
        db.add(AIConfig(user_id=uid,create_request_id=uuid4(),create_fingerprint='x'*64,name='原有模型合成入口',
            base_url='https://example.com/v1',model_id='synthetic-model',encrypted_key='unused',key_version='unused',enabled=True,is_default=True))
    anonymous=client.cookies.get('camp_session');client.cookies.clear()
    assert client.get('/api/ai/supabase').status_code==401
    assert client.post('/api/ai/supabase/public-key/copy',headers={'Origin':'http://testserver'}).status_code==401
    client.cookies.set('camp_session',anonymous)
    assert client.get('/api/ai/supabase').json()['configured']
    assert client.get('/api/ai/configs').json()[0]['name']=='原有模型合成入口'
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        assert server.started
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':1366,'height':900},permissions=['clipboard-read','clipboard-write'])
            base=f'http://127.0.0.1:{port}'
            page.context.add_cookies([{'name':'camp_session','value':str(uid),'url':base}])
            errors=[];responses=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            def inspect_response(response):
                if '/api/ai/' in response.url:
                    body=response.text();assert private not in body
                    if '/public-key/copy' not in response.url:assert public not in body
                    responses.append(response.url)
            page.on('response',inspect_response)
            page.goto(base+'/spirit-stones')
            page.locator('#ai-list').get_by_text('原有模型合成入口',exact=True).wait_for()
            page.locator('#supabase-status').get_by_text('配置状态：已配置',exact=True).wait_for()
            page.locator('#supabase-card h3').click()
            assert page.locator('#supabase-detail').is_visible()
            assert page.locator('#supabase-project-url').input_value()==project
            assert '••••••••' in page.locator('#supabase-public-key').input_value()
            assert private not in page.content() and public not in page.content()
            page.get_by_role('button',name='复制 Project URL',exact=True).click()
            page.get_by_text('Project URL 已复制。',exact=True).wait_for()
            assert page.evaluate('navigator.clipboard.readText()')==project
            page.get_by_role('button',name='复制公开 API Key',exact=True).click()
            page.get_by_text('公开 API Key 已复制。',exact=True).wait_for()
            assert page.evaluate('navigator.clipboard.readText()')==public
            link=page.locator('#supabase-dashboard-detail')
            assert link.get_attribute('href')=='https://supabase.com/dashboard/project/'+'a'*20
            assert link.get_attribute('target')=='_blank'
            page.locator('#ai-list').get_by_role('button',name='编辑',exact=True).click()
            assert page.locator('#ai-form [name=name]').input_value()=='原有模型合成入口'
            app.state.settings=Settings(_env_file=None)
            page.reload()
            page.locator('#supabase-status').get_by_text('配置状态：未配置',exact=True).wait_for()
            page.get_by_role('button',name='查看配置',exact=True).click()
            assert page.locator('#supabase-project-url').input_value()=='未配置'
            assert page.locator('#supabase-public-key').input_value()=='未配置'
            assert page.locator('#supabase-copy-url').is_disabled() and page.locator('#supabase-copy-key').is_disabled()
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors and responses
            browser.close()
    finally:
        server.should_exit=True;thread.join(10);sock.close()
