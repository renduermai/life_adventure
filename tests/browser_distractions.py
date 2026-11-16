"""Browser contract with synthetic API responses; does not write a real database."""
import sys, threading, time
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright, expect
from app.core.config import Settings
from app.main import create_app


def run():
    app = create_app(Settings(_env_file=None, log_level='ERROR'))
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8768, log_level='error', access_log=False))
    threading.Thread(target=server.run, daemon=True).start()
    items, requests = [], []
    state = {'failure': False, 'unauthorized': False}
    def respond(route):
        req = route.request
        assert '/api/distractions/notes' in req.url
        if state['unauthorized']:
            route.fulfill(status=401, json={'error':'unauthorized'}); return
        if req.method == 'GET':
            route.fulfill(json={'items':items, 'next_offset':None}); return
        data = req.post_data_json
        requests.append((req.method, data))
        if state['failure']:
            route.fulfill(status=503, json={'error':'暂时无法保存'}); return
        if req.method == 'POST':
            item = dict(id=str(uuid4()), content=data['content'], version=1, created_at='2026-11-16T08:00:00Z', updated_at='2026-11-16T08:00:00Z')
            items.insert(0,item); route.fulfill(json=item); return
        items[:] = [x for x in items if x['id'] != req.url.rsplit('/',1)[-1]]
        route.fulfill(json={'deleted':True})
    try:
        for _ in range(100):
            if server.started: break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width':1440,'height':900})
            errors=[]
            page.on('pageerror',lambda e: errors.append(str(e)))
            page.route('**/api/**',respond)
            page.goto('http://127.0.0.1:8768/distractions')
            expect(page.locator('#thought-list')).to_contain_text('还没有记录')
            expect(page.locator('a.nav-item.active')).to_contain_text('杂念')
            assert page.get_by_role('button',name='✦ AI 一键归类').is_disabled()
            state['failure']=True
            page.locator('#thought-input').fill('  测试\n<img src=x onerror=alert(1)>  ')
            page.locator('#thought-send').click()
            expect(page.locator('#thought-message')).to_contain_text('暂时无法保存')
            assert page.locator('#thought-input').input_value().startswith('  测试')
            state['failure']=False
            page.locator('#thought-send').click()
            expect(page.locator('.thought-item')).to_have_count(1)
            assert requests[0][1]['request_id'] == requests[1][1]['request_id']
            assert page.locator('#thought-list img').count()==0
            expect(page.locator('#thought-detail')).to_contain_text('<img src=x')
            page.locator('#thought-input').fill('另一个念头')
            page.locator('#thought-send').click()
            expect(page.locator('.thought-item')).to_have_count(2)
            page.reload()
            expect(page.locator('.thought-item')).to_have_count(2)
            page.locator('.thought-select').last.click()
            expect(page.locator('#thought-detail')).to_contain_text('测试')
            page.on('dialog',lambda dialog:dialog.accept())
            page.locator('.thought-delete').last.click()
            expect(page.locator('.thought-item')).to_have_count(1)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.locator('#thought-detail').is_visible()
            state['unauthorized']=True
            page.reload()
            expect(page.locator('#thought-message')).to_contain_text('请先登录')
            assert not errors,errors
            browser.close()
        print('Browser synthetic contract passed: desktop/mobile, retry, reload, delete, XSS, auth')
    finally:
        server.should_exit=True

if __name__ == '__main__': run()
