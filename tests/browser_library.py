"""Synthetic browser checks for failed saves and stable retry identifiers."""
import sys, threading, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright, expect
from app.main import create_app
from app.core.config import Settings


def run():
    app=create_app(Settings(_env_file=None,log_level='ERROR'))
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8767,log_level='error',access_log=False))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    state={'fail':True,'requests':[],'items':[]}
    def route(r):
        req=r.request
        if req.url.endswith('/targets'):
            r.fulfill(json={'quests':[{'id':'00000000-0000-0000-0000-000000000001','title':'主线'}],'tasks':[]});return
        if req.method=='GET':
            r.fulfill(json={'items':state['items'],'next_offset':None});return
        payload=req.post_data_json;state['requests'].append(payload)
        if state['fail']:
            r.fulfill(status=503,json={'error':'暂时无法保存'});return
        state['items']=[{'id':'00000000-0000-0000-0000-000000000003','description':payload['description'],'url':payload['url'],'main_quest_id':payload['main_quest_id'],'task_id':None,'target_title':'主线','version':1,'click_count':0}]
        r.fulfill(json=state['items'][0])
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True);page=browser.new_page();page.route('**/api/library/**',route)
            page.goto('http://127.0.0.1:8767/library')
            page.locator('#library-description').fill('保留输入')
            page.locator('#library-url').fill('https://example.com/')
            page.locator('#library-target').select_option('main_quest_id:00000000-0000-0000-0000-000000000001')
            page.locator('#library-submit').click();expect(page.locator('#library-form-message')).to_contain_text('暂时无法保存')
            assert page.locator('#library-description').input_value()=='保留输入'
            state['fail']=False;page.locator('#library-submit').click()
            expect(page.locator('#library-list')).to_contain_text('保留输入')
            assert state['requests'][0]['request_id']==state['requests'][1]['request_id']
            assert page.locator('#library-target').input_value()=='main_quest_id:00000000-0000-0000-0000-000000000001'
            browser.close()
        print('Library synthetic retry and input preservation passed')
    finally:
        server.should_exit=True;thread.join(timeout=10)

if __name__=='__main__':run()
