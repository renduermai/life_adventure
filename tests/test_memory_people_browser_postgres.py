import socket,time,threading
from uuid import uuid4
import pytest
import uvicorn
from playwright.sync_api import sync_playwright
from test_distractions_postgres import notes,task_engine
from test_memory_person_analysis_postgres import setup
from test_memory_person_analysis import output
from app.modules.ai_gateway.service import AIService

pytestmark=pytest.mark.integration


def test_people_events_analysis_browser(notes,monkeypatch):
    client,sessions,uid,other,app,person,url=setup(notes)
    calls=[]
    def generate(*args,**kwargs):calls.append(1);return {'content':output()}
    monkeypatch.setattr(AIService,'generate',generate)
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
            page=browser.new_page(viewport={'width':1366,'height':900});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.context.add_cookies([{'name':'camp_session','value':str(uid),'url':f'http://127.0.0.1:{port}'}])
            page.goto(f'http://127.0.0.1:{port}/shining-memories/people')
            page.get_by_role('button',name='查看 合成老师',exact=True).click()
            page.get_by_role('button',name='预览发送范围',exact=True).click()
            page.get_by_text('请核对范围，再勾选确认。',exact=True).wait_for()
            assert not calls
            assert not page.get_by_label('允许参考主线、副本',exact=True).is_checked()
            assert not page.get_by_label('允许参考杂念',exact=True).is_checked()
            page.get_by_label('我已核对预览，允许将这些内容发送到上述外部模型。',exact=True).check()
            page.get_by_role('button',name='确认并分析',exact=True).click()
            page.get_by_text('分析已保存。',exact=True).wait_for(timeout=20000)
            assert len(calls)==1
            page.locator('#person-analysis').get_by_text('给予机会的老师',exact=True).wait_for()
            page.locator('#event-form [name=event_date]').fill('2026-01-01')
            page.locator('#event-form [name=content]').fill('浏览器合成回忆，不是实际联系')
            page.get_by_role('button',name='保存事件',exact=True).click()
            page.get_by_text('事件已保存。',exact=True).wait_for()
            page.locator('#person-analysis').get_by_text('旧分析已过期，请重新预览后分析。',exact=True).wait_for()
            page.reload();page.get_by_role('button',name='查看 合成老师',exact=True).click()
            page.get_by_text('浏览器合成回忆，不是实际联系',exact=True).wait_for()
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors,errors
            from app.modules.distractions.models import DistractionNote
            nid=uuid4()
            with sessions.begin() as db:db.add(DistractionNote(id=nid,user_id=uid,content='浏览器合成杂念详情',create_request_id=uuid4(),create_fingerprint='b'*64))
            page.goto(f'http://127.0.0.1:{port}/distractions?note_id={nid}')
            page.locator('.thought-full').filter(has_text='浏览器合成杂念详情').wait_for()
            assert not errors,errors
            browser.close()
    finally:
        server.should_exit=True;thread.join(10);sock.close()
