import socket,threading,time
import pytest,uvicorn
from playwright.sync_api import sync_playwright
from test_distractions_postgres import notes,task_engine
pytestmark=pytest.mark.integration

def test_draft_navigation_and_layout(notes):
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
            page=browser.new_page(viewport={'width':1366,'height':900});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.context.add_cookies([{'name':'camp_session','value':str(uid),'url':f'http://127.0.0.1:{port}'}])
            page.goto(f'http://127.0.0.1:{port}/shining-memories/items')
            page.get_by_role('button',name='＋ 添加物品').click()
            page.locator('#item-form [name=name]').fill('未保存草稿')
            seen=[]
            def reject(dialog):seen.append(dialog.message);dialog.dismiss()
            page.once('dialog',reject)
            page.get_by_role('link',name='心愿单',exact=True).click()
            assert seen and '尚未保存' in seen[0]
            assert page.url.endswith('/items') and page.locator('#item-form [name=name]').input_value()=='未保存草稿'
            page.once('dialog',lambda dialog:dialog.accept())
            page.get_by_role('link',name='心愿单',exact=True).click()
            assert page.url.endswith('/wishes')
            for section in ('people','items','wishes'):
                page.set_viewport_size({'width':390,'height':844})
                page.goto(f'http://127.0.0.1:{port}/shining-memories/{section}')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert page.locator('.memory-tab[aria-current=page]').count()==1
            assert not errors,errors
            browser.close()
    finally:server.should_exit=True;thread.join(10);sock.close()
