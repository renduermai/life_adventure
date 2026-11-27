import socket,time,threading
import pytest,uvicorn
from playwright.sync_api import sync_playwright
from test_distractions_postgres import notes,task_engine
pytestmark=pytest.mark.integration

def test_wish_story_prices_correction_browser(notes):
    client,sessions,uid,other,app=notes
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
            page.goto(f'http://127.0.0.1:{port}/shining-memories/wishes')
            page.get_by_role('button',name='＋ 新增心愿').click()
            page.locator('#wish-form [name=name]').fill('合成旅行')
            page.locator('#wish-form [name=reason]').fill('希望休息')
            page.locator('#wish-form [name=price]').fill('5000')
            page.locator('#wish-form [name=category]').fill('旅行')
            page.get_by_role('button',name='保存心愿',exact=True).click()
            page.get_by_text('心愿已保存。',exact=True).wait_for()
            page.locator('#wish-price-form [name=price]').fill('4200')
            page.get_by_role('button',name='保存价格',exact=True).click()
            page.get_by_text('价格已保存。',exact=True).wait_for()
            assert '16.00%' in page.locator('#wish-story').inner_text()
            page.reload();page.get_by_role('button',name='查看 合成旅行',exact=True).click()
            page.locator('#wish-price-form [name=price]').fill('6000')
            page.locator('#wish-price-form [name=correct]').check()
            page.locator('#wish-price-form [name=note]').fill('首次填写错误')
            page.once('dialog',lambda d:d.accept())
            page.get_by_role('button',name='保存价格',exact=True).click()
            page.get_by_text('价格已保存。',exact=True).wait_for()
            assert '纠正后的首次价格' in page.locator('#wish-story').inner_text()
            assert '4200.00' in page.locator('#wish-story').inner_text()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors,errors
            browser.close()
    finally:server.should_exit=True;thread.join(10);sock.close()
