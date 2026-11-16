"""Synthetic HTTP checks for independent classifications and dense scatter UI."""
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright, expect
from app.main import create_app
from app.core.config import Settings


def run():
    app = create_app(Settings(_env_file=None, log_level='ERROR'))
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8771, log_level='error', access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    items = [dict(id=str(uuid4()), description=title, importance=85, urgency=80,
        progress='已完成一部分', version=1, analysis={'status': 'pending', 'result': None})
        for title in ['完善代码评测', '整理桌面', '阅读技术文章']]
    calls = []
    failed_once = False
    state = {'generation': 0, 'state': None}

    def respond(route):
        nonlocal failed_once, state
        request = route.request
        url = urlsplit(request.url)
        path = url.path
        if path == '/api/startup/current':
            value = state
        elif path == '/api/startup/states':
            state = dict(request.post_data_json, generation=state['generation'] + 1, snapshot_id=str(uuid4()))
            value = state
        elif path == '/api/startup/chat/conversations':
            value = {'items': [], 'next_offset': None}
        elif path == '/api/startup/items':
            offset = int(parse_qs(url.query).get('offset', [0])[0])
            value = {'items': items[offset:offset+20], 'next_offset': offset+20 if len(items)>offset+20 else None}
        elif path.startswith('/api/startup/items/'):
            identifier = path.split('/')[4]
            item = next(x for x in items if x['id'] == identifier)
            if path.endswith('/analyze'):
                cached = bool(item['analysis'].get('result'))
                if not cached:
                    calls.append(identifier)
                    if item is items[1] and not failed_once:
                        failed_once = True
                        item['analysis'] = {'status': 'failed', 'result': None, 'error': '模型响应超时', 'error_code': 'upstream_timeout'}
                    else:
                        index = items.index(item)
                        item['analysis'] = {'status': 'analyzed', 'result': {'item_id': identifier,
                            'keyword': item['description'], 'quadrant': ['投入区','修复区','激活区'][index % 3],
                            'reason': '结合内容与启动难度分析', 'action': '先打开材料，只看一段'}}
                value = {'item': item, 'cached': cached}
            elif request.method == 'PATCH':
                item.update(request.post_data_json)
                item['version'] += 1
                item['analysis'] = {'status': 'stale', 'result': None, 'previous_result': item['analysis']['result']}
                value = item
            else:
                value = item
        else:
            raise AssertionError(path)
        route.fulfill(json=value)

    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1100})
            errors = []
            page.on('pageerror', lambda exc: errors.append(str(exc)))
            page.route('**/api/**', respond)
            page.goto('http://127.0.0.1:8771/startup')
            page.locator('#items-analyze').click()
            expect(page.locator('#items-analysis-message')).to_contain_text('失败 1 件')
            expect(page.locator('.item-marker')).to_have_count(2)
            card = page.locator('[data-item-id="' + items[1]['id'] + '"]').filter(has=page.locator('h3'))
            card.get_by_role('button', name='分析这件事').click()
            expect(page.locator('.item-marker')).to_have_count(3)
            page.locator('#items-analyze').click()
            expect(page.locator('#items-analysis-message')).to_contain_text('复用 3 件缓存')
            assert len(calls) == 4
            page.reload()
            expect(page.locator('.item-marker')).to_have_count(3)
            assert len(calls) == 4
            marker = page.locator('.item-marker').first
            marker.hover()
            expect(page.locator('#item-scatter-tooltip')).to_contain_text('重要程度 85')
            expect(page.locator('#item-scatter-tooltip')).to_contain_text('只看一段')
            marker.click()
            expect(page.locator('#item-form')).to_be_visible()
            expect(page.locator('#item-form-message')).to_contain_text('结合内容')
            page.locator('#item-description').fill('内容已经变化')
            page.locator('#item-form button[type=submit]').click()
            expect(page.locator('.item-marker')).to_have_count(2)
            expect(page.locator('#items-list')).to_contain_text('待重新分析')
            page.evaluate('''() => {for(const [id,value] of [['pressure',80],['energy',25]]){const el=document.getElementById(id);el.value=value;el.dispatchEvent(new Event('input'));}}''')
            expect(page.locator('.item-marker.matches-state')).to_have_count(1)
            expect(page.locator('#state-message')).to_have_text('已自动保存')
            assert len(calls) == 4
            # More than the old 12-slot limit: all 40 remain visible, including pages beyond 20.
            template = next(x for x in items if x['analysis'].get('result'))
            items[:] = [dict(template, id=str(uuid4())) for _ in range(40)]
            page.set_viewport_size({'width': 390, 'height': 844})
            page.reload()
            expect(page.locator('.item-marker')).to_have_count(40)
            positions = page.locator('.item-marker').evaluate_all('(nodes)=>nodes.map(n=>n.style.left+","+n.style.top)')
            assert len(set(positions)) == 40
            geometry = page.locator('.item-marker').evaluate_all('''nodes=>nodes.map(n=>{const p=n.parentElement.getBoundingClientRect(),r=n.getBoundingClientRect();return {x:(r.x+r.width/2-p.x)/p.width,y:(r.y+r.height/2-p.y)/p.height,q:n.dataset.quadrant};})''')
            for point in geometry:
                if point['q'] == '修复区':
                    assert .5 < point['x'] < 1 and .5 < point['y'] < 1
                elif point['q'] == '激活区':
                    assert 0 < point['x'] < .5 and .5 < point['y'] < 1
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors, errors
            browser.close()
            print('PASS: partial/retry/cache/reload/tooltip/edit-stale/no-slider-AI/40 points/390px; synthetic HTTP')
    finally:
        server.should_exit = True
        thread.join(10)


if __name__ == '__main__':
    run()
