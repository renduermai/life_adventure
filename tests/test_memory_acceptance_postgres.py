import socket,threading,time
from uuid import uuid4
import pytest,uvicorn
from playwright.sync_api import sync_playwright
from test_distractions_postgres import notes,task_engine
from test_memory_media import FakeStorage,picture
from app.modules.shining_memories.shared import service as media
from app.modules.shining_memories.shared.images import normalize_image

pytestmark=pytest.mark.integration
H={'Origin':'http://testserver'}

def test_image_failure_replacement_and_category_error(notes,monkeypatch):
    client,sessions,uid,other,app=notes
    from app.modules.shining_memories import router
    store=FakeStorage();monkeypatch.setattr(router,'storage',lambda request,bucket=None:store)
    asset=media.upload(app.state.database,store,uid,normalize_image(picture(),'old.png'),uuid4())
    original=client.post('/api/shining-memories/items',headers=H,json={'request_id':str(uuid4()),'name':'联调合成物品','purchase_date':'2026-01-01','purchase_price':'100','category':'联调类别','image_asset_id':str(asset['id'])})
    assert original.status_code==200,original.text
    iid=original.json()['id']
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False));thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
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
            page.get_by_role('button',name='编辑 联调合成物品',exact=True).click()
            page.locator('[name=image]').set_input_files({'name':'new.png','mimeType':'image/png','buffer':picture(color='blue')})
            store.failure=True
            page.get_by_role('button',name='保存物品',exact=True).click()
            page.get_by_text('输入已保留。',exact=False).wait_for()
            assert page.locator('[name=name]').input_value()=='联调合成物品'
            assert client.get('/api/shining-memories/items/'+iid).json()['image_asset_id']==str(asset['id'])
            store.failure=False
            page.locator('[name=image]').set_input_files({'name':'retry.png','mimeType':'image/png','buffer':picture(color='blue')})
            page.get_by_role('button',name='保存物品',exact=True).click()
            page.get_by_text('物品已保存。',exact=True).wait_for()
            changed=client.get('/api/shining-memories/items/'+iid).json()
            assert changed['image_asset_id']!=str(asset['id'])
            assert client.get('/api/shining-memories/assets/'+str(asset['id'])).status_code==404
            page.route('**/api/shining-memories/items?*',lambda route:route.fulfill(status=503,content_type='application/json',body='{"error":"合成筛选故障"}'))
            page.locator('#item-filter').select_option(label='联调类别')
            page.get_by_text('合成筛选故障 请重新读取。',exact=True).wait_for()
            assert page.locator('#item-list .item-card').count()==0
            assert not errors,errors
            browser.close()
    finally:server.should_exit=True;thread.join(10);sock.close()
