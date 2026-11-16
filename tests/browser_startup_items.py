"""Independent item UI contract: synthetic HTTP, no AI or database writes."""
import sys
import tempfile
import threading
import time
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright, expect
from app.core.config import Settings
from app.main import create_app


def run():
    app = create_app(Settings(_env_file=None, log_level='ERROR'))
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8769, log_level='error', access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    items = []
    fail_save = False
    writes = []

    def respond(route):
        request = route.request
        path = request.url.split('8769')[1].split('?')[0]
        if path == '/api/startup/current':
            result = {'generation': 0, 'state': None}
        elif path == '/api/startup/chat/conversations':
            result = {'items': [], 'next_offset': None}
        elif path.startswith('/api/startup/items'):
            if request.method == 'GET':
                result = {'items': items, 'next_offset': None}
            else:
                data = request.post_data_json
                writes.append((request.method, data))
                if fail_save:
                    route.fulfill(status=503, json={'error': 'Synthetic offline'})
                    return
                if request.method == 'POST':
                    result = dict(data, id=str(uuid4()), version=1)
                    items.insert(0, result)
                else:
                    item = next(x for x in items if x['id'] == path.rsplit('/', 1)[1])
                    assert data['expected_version'] == item['version']
                    if request.method == 'PATCH':
                        item.update(data)
                        item['version'] += 1
                        result = item
                    else:
                        items.remove(item)
                        result = {'deleted': True}
        else:
            raise AssertionError(path)
        route.fulfill(json=result)

    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda exc: errors.append(str(exc)))
            page.route('**/api/**', respond)
            page.goto('http://127.0.0.1:8769/startup')
            expect(page.locator('#items-list')).to_contain_text('还没有记录事情')
            for index, text in enumerate(['检查几个 Bug', '看看 AI 工具', '<img src=x onerror=alert(1)>']):
                page.locator('#item-new').click()
                page.locator('#item-description').fill(text)
                page.locator('#item-progress').fill('已定位两个' if index == 0 else '')
                page.locator('#item-importance').fill('85')
                page.locator('#item-urgency').fill('80')
                page.locator('#item-form button[type=submit]').click()
                expect(page.locator('.startup-item')).to_have_count(index + 1)
            assert (items[-1]['importance'], items[-1]['urgency'], items[-1]['progress']) == (85, 80, '已定位两个')
            assert page.locator('#items-list img').count() == 0
            page.locator('.startup-item').last.get_by_role('button', name='编辑').click()
            expect(page.locator('#item-progress')).to_have_value('已定位两个')
            page.locator('#item-progress').fill('已修复一个')
            fail_save = True
            page.locator('#item-form button[type=submit]').click()
            expect(page.locator('#item-form-message')).to_contain_text('Synthetic offline')
            expect(page.locator('#item-progress')).to_have_value('已修复一个')
            fail_save = False
            page.locator('#item-form button[type=submit]').click()
            expect(page.locator('#item-form')).to_be_hidden()
            page.reload()
            expect(page.locator('.startup-item').last).to_contain_text('已修复一个')
            page.once('dialog', lambda dialog: dialog.dismiss())
            page.locator('.startup-item').last.get_by_role('button', name='删除').click()
            expect(page.locator('.startup-item')).to_have_count(3)
            page.once('dialog', lambda dialog: dialog.accept())
            page.locator('.startup-item').last.get_by_role('button', name='删除').click()
            expect(page.locator('.startup-item')).to_have_count(2)
            expect(page.get_by_role('button', name='开始分析')).to_be_enabled()
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('#item-new').click()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            out = Path(tempfile.gettempdir()) / 'adventure-v3-items'
            out.mkdir(exist_ok=True)
            page.screenshot(path=str(out / 'mobile.png'), full_page=True)
            assert not errors, errors
            browser.close()
            print('PASS: multiple create / four fields / edit / failure preserves draft / reload / cancel-delete / confirm-delete / text safety / 390px; synthetic HTTP')
    finally:
        server.should_exit = True
        thread.join(10)


if __name__ == '__main__':
    run()
