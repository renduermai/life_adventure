"""Real Edge checks for layer experience, mode, and scene editors."""
import socket
import threading
import time

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright
from uuid import uuid4
from datetime import datetime, timezone
from app.modules.life_os.models import Analysis, Message
from app.modules.life_os.later_service import apply_analysis_mode
from test_distractions_postgres import notes
from test_tasks_postgres import task_engine

pytestmark=pytest.mark.integration


def test_life_os_later_features_responsive(notes):
    api_client,sessions,uid,_,app=notes
    with sessions.begin() as db:
        message=Message(user_id=uid,request_id=uuid4(),content='合成快照：工作空间影响行动。');db.add(message);db.flush()
        analysis=Analysis(user_id=uid,message_id=message.id,request_id=uuid4(),status='succeeded',result={'reply':'合成回复','energy':{'value':40,'reason':'合成理由'},'bandwidth':{'value':50,'reason':'合成理由'},'order':{'value':30,'reason':'合成理由'},'core_conflict':'合成层次冲突依据','life_layers':['生活秩序'],'need_layers':['安全'],'suggested_mode':'yellow'},source_ids=[str(message.id)],prompt_version='browser-fixture',finished_at=datetime.now(timezone.utc));db.add(analysis);db.flush();apply_analysis_mode(db,uid,analysis)
    snapshot=api_client.get('/api/life-os/messages').json()['state']
    assert snapshot['result']['life_layers']==['生活秩序']
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':1366,'height':900});errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.context.add_cookies([{'name':'camp_session','value':str(uid),'url':f'http://127.0.0.1:{port}'}])
            page.goto(f'http://127.0.0.1:{port}/life-os')
            expect(page.get_by_role('heading',name='人生运行系统')).to_be_visible()
            page.wait_for_selector('#life-layers button[data-layer="生活秩序"][aria-pressed="true"]',timeout=10000)
            expect(page.locator('#life-layers li.is-highlighted')).to_have_count(1)
            expect(page.locator('#layer-evidence')).to_contain_text('合成层次冲突依据')
            expect(page.locator('#life-mode-summary')).to_contain_text('AI 建议：黄色 · 稳定运行')
            page.locator('.life-os-layer-card button[data-model="life"][data-layer="生活秩序"]').click()
            experience=page.locator('.life-os-exp-form').last
            experience.locator('input[name=occurred_on]').fill('2026-11-26')
            experience.locator('textarea[name=event]').fill('合成测试桌面杂乱')
            experience.locator('textarea[name=experience]').fill('合成测试先收拾一个角落')
            experience.get_by_role('button',name='保存经验').click()
            expect(page.locator('.life-os-exp-card')).to_contain_text('合成测试先收拾一个角落')
            page.locator('#life-mode-list button[data-mode="blue"]').click()
            expect(page.locator('#life-mode-summary')).to_contain_text('蓝色 · 重启恢复')
            page.get_by_role('button',name='＋ 新建场景').click()
            editor=page.locator('.life-os-scene-editor').last
            editor.locator('input[name=name]').fill('合成场景')
            editor.get_by_role('button',name='＋ 添加每日时段').click()
            editor.locator('.life-os-daily-row input[placeholder="活动内容"]').fill('合成活动')
            editor.get_by_role('button',name='保存场景').click()
            expect(page.locator('#life-scene-toolbar')).to_contain_text('合成场景')
            expect(page.locator('#life-daily-schedule')).to_contain_text('合成活动')
            expect(page.locator('#life-daily-schedule .life-os-time-label')).to_have_count(5)
            expect(page.locator('#life-daily-schedule .life-os-time-marker')).to_have_count(1)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors,errors
            browser.close()
    finally:
        server.should_exit=True;thread.join(10)
