import socket
import threading
import time
import pytest
import uvicorn
from playwright.sync_api import sync_playwright, expect
from test_library_postgres import setup, notes, task_engine

pytestmark = pytest.mark.integration


def test_library_browser_real_database(notes):
    client,sessions,uid,other,q,t,foreign,app=setup(notes)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started: break
            time.sleep(.05)
        assert server.started
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            context=browser.new_context(viewport={'width':1440,'height':900})
            context.add_cookies([{'name':'camp_session','value':str(uid),'url':f'http://127.0.0.1:{port}'}])
            page=context.new_page();errors=[];page.on('pageerror',lambda exc:errors.append(str(exc)))
            page.goto(f'http://127.0.0.1:{port}/library?target_type=task&target_id={t}')
            expect(page.locator('.nav-item.active')).to_contain_text('藏经阁')
            expect(page.locator('#library-list')).to_contain_text('书架还是空的',timeout=20000)
            page.locator('#library-description').fill('<img src=x onerror=alert(1)>')
            page.locator('#library-url').fill('https://example.com/docs')
            page.locator('#library-target').select_option('task_id:'+str(t))
            page.locator('#library-submit').click()
            expect(page.locator('.library-item')).to_have_count(1,timeout=20000)
            expect(page.locator('#library-list')).to_contain_text('<img src=x')
            assert page.locator('#library-list img').count()==0
            assert page.locator('#library-target').input_value()=='task_id:'+str(t)
            assert page.locator('#library-filter').input_value()=='task_id:'+str(t)
            page.evaluate("Object.defineProperty(navigator,'clipboard',{value:{writeText:async()=>{throw Error('denied')}},configurable:true})")
            page.get_by_role('button',name='复制',exact=True).click()
            expect(page.locator('#library-list')).to_contain_text('已复制 0 次')
            page.evaluate("Object.defineProperty(navigator,'clipboard',{value:{writeText:async()=>{}},configurable:true})")
            page.get_by_role('button',name='复制',exact=True).click()
            expect(page.locator('#library-list')).to_contain_text('已复制 1 次',timeout=15000)
            page.get_by_role('button',name='复制',exact=True).click()
            expect(page.locator('#library-list')).to_contain_text('已复制 2 次',timeout=15000)
            page.locator('.library-item select').select_option('main_quest_id:'+str(q))
            expect(page.locator('.library-item')).to_have_count(0,timeout=15000)
            page.locator('#library-filter').select_option('main_quest_id:'+str(q))
            expect(page.locator('.library-item')).to_have_count(1,timeout=15000)
            assert page.locator('.library-link').get_attribute('target')=='_blank'
            assert 'noopener' in page.locator('.library-link').get_attribute('rel')
            page.reload();expect(page.locator('.library-item')).to_have_count(1,timeout=20000)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.on('dialog',lambda d:d.accept())
            page.get_by_role('button',name='删除链接：<img src=x onerror=alert(1)>').click()
            expect(page.locator('.library-item')).to_have_count(0,timeout=20000)
            page.reload();expect(page.locator('#library-list')).to_contain_text('书架还是空的',timeout=20000)
            context.clear_cookies();page.reload()
            expect(page.locator('#library-message')).to_contain_text('请先登录',timeout=20000)
            assert not errors, errors
            browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=10)
