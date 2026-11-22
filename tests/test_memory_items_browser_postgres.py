import socket,threading,time
import pytest,uvicorn
from playwright.sync_api import sync_playwright
from test_distractions_postgres import notes,task_engine
pytestmark=pytest.mark.integration

def test_items_browser_without_storage(notes):
    client,sessions,uid,other,app=notes
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        assert server.started
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':390,'height':844});errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.context.add_cookies([{'name':'camp_session','value':str(uid),'url':f'http://127.0.0.1:{port}'}])
            page.goto(f'http://127.0.0.1:{port}/shining-memories/items')
            page.get_by_role('button',name='＋ 添加物品').click()
            page.locator('[name=name]').fill('合成键盘')
            page.locator('[name=purchase_date]').fill('2026-01-01')
            page.locator('[name=purchase_price]').fill('120')
            page.locator('[name=category]').fill('电子产品')
            page.get_by_role('button',name='保存物品').click()
            page.get_by_text('物品已保存。').wait_for()
            page.reload();page.get_by_text('合成键盘',exact=True).wait_for()
            page.locator('#item-filter').select_option(label='电子产品')
            page.get_by_text('合成键盘',exact=True).wait_for()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors,errors
            browser.close()
    finally:server.should_exit=True;thread.join(10);sock.close()
