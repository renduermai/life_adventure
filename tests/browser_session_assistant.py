"""V3 session assistant browser contract with synthetic HTTP responses."""
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright,expect
from app.core.config import Settings
from app.main import create_app


def run():
    server=uvicorn.Server(uvicorn.Config(create_app(Settings(_env_file=None,log_level='ERROR')),host='127.0.0.1',port=8773,log_level='error',access_log=False))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    owner,tid=str(uuid4()),str(uuid4())
    calls=[];failure=False;target_valid=True
    target=dict(kind='task',id=tid,title='整理测试目录',description='已建立目录，准备检查文件',href='/tasks/'+tid,steps=[],main_quest='独立副本',progress=0,status='todo')
    def respond(route):
        request=route.request;path=request.url.split('8773')[1].split('?')[0]
        if path=='/api/startup/chat/context':
            selected='task_id=' in request.url
            if selected and not target_valid:route.fulfill(status=404,json={'error':'任务已删除','code':'not_found'});return
            value={'owner_id':owner,'target':target if selected else None}
        elif path=='/api/startup/chat/messages':
            data=request.post_data_json;calls.append(data)
            assert data['owner_id']==owner
            if failure:route.fulfill(status=504,json={'error':'模型响应超时','code':'upstream_timeout'});return
            clarify=data['mode']=='breakdown' and not data['history']
            steps=[] if data['mode']=='free' or clarify else [dict(title='只打开文件夹',detail='不用整理全部文件',minutes=1,done_when='看到目录即可')]
            value={'response':dict(reply='今天希望推进到哪里？' if clarify else '先打开文件夹即可。',needs_clarification=clarify,understanding='整理目录' if steps else '',completed='目录已建立' if steps else '',today_goal='十分钟内看一眼' if steps else '',steps=steps,minimum_action='只打开目录' if steps else '')}
        elif path=='/api/startup/current':value={'generation':0,'state':None}
        elif path=='/api/startup/items':value={'items':[],'next_offset':None}
        else:raise AssertionError(path)
        route.fulfill(json=value)
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000},reduced_motion='reduce');errors=[]
            page.on('pageerror',lambda exc:errors.append(str(exc)));page.route('**/api/**',respond)
            page.add_init_script("Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{window.copiedSteps=text;}}});")
            page.goto('http://127.0.0.1:8773/startup')
            expect(page.locator('#chat-input')).to_be_enabled();expect(page.locator('#chat-mode')).to_have_text('自由对话')
            page.locator('#chat-input').fill('我有点焦虑');page.locator('#chat-form button').click()
            expect(page.locator('.chat-answer')).to_have_count(1)
            assert calls[-1]['history']==[] and not calls[-1]['include_tasks']
            page.reload();expect(page.locator('.chat-answer')).to_have_count(1);assert len(calls)==1
            page.once('dialog',lambda dialog:dialog.accept());page.locator('#chat-new').click()
            expect(page.locator('.chat-answer')).to_have_count(0)
            url='http://127.0.0.1:8773/startup?task_type=task&task_id='+tid+'&generate='+str(uuid4())+'#chat'
            page.goto(url);expect(page.locator('.chat-answer')).to_contain_text('今天希望推进到哪里')
            expect(page.locator('#chat-target')).to_contain_text('整理测试目录')
            assert 'generate=' not in page.url and len(calls)==2
            page.locator('#chat-input').fill('只有十分钟，第一步还是太难');page.locator('#chat-form button').click()
            expect(page.locator('.chat-answer').last).to_contain_text('最小启动动作')
            assert len(calls[-1]['history'])==1 and calls[-1]['task_id']==tid
            page.get_by_role('button',name='复制步骤',exact=True).click();assert '只打开文件夹' in page.evaluate('window.copiedSteps')
            page.reload();expect(page.locator('.chat-answer')).to_have_count(2);assert len(calls)==3
            failure=True;page.locator('#chat-input').fill('再小一点');page.locator('#chat-form button').click()
            expect(page.locator('#chat-status')).to_contain_text('模型响应超时');expect(page.locator('#chat-input')).to_have_value('再小一点')
            expect(page.locator('.chat-answer')).to_have_count(2);failure=False
            page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            owner=str(uuid4());page.reload();expect(page.locator('#chat-input')).to_be_enabled();expect(page.locator('.chat-answer')).to_have_count(0)
            target_valid=False;page.reload();expect(page.locator('#chat-mode')).to_have_text('自由对话');expect(page.locator('#chat-status')).to_contain_text('任务已删除')
            assert not errors,errors
            browser.close();print('PASS session free/breakdown/clarify/feedback/copy/reload/no-auto-rebill/reset/account-isolation/deleted-target/failure/390px; synthetic HTTP')
    finally:server.should_exit=True;thread.join(10)


if __name__=='__main__':run()
