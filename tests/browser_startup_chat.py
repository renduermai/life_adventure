"""Opt-in headless UI contract test, with synthetic HTTP responses (no AI/DB).

Run: .venv/Scripts/python.exe tests/browser_startup_chat.py
Install requirements-browser.txt and Microsoft Edge first.
"""
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright, expect
from app.core.config import Settings
from app.main import create_app


def run():
    app = create_app(Settings(_env_file=None, log_level='ERROR'))
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8766, access_log=False, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    saved = None
    turns = []
    batch = None
    refresh_fails = False
    partial_mode = False
    current_items = []
    retry_targets = []
    calls = []
    sid, cid = '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002'
    stamp = '2026-11-15T08:00:00+08:00'
    item = dict(key='task:example', kind='task', title='整理桌面', description='先整理一支笔',
                main_quest='让工作区更清爽', keyword='整理一支笔', href='/tasks/example',
                quadrants=['降噪区'], level='green', reason='动作很小，适合起步',
                stale=False, analysis_status='analyzed', analysis_id=sid, analysis_version=1)

    def respond(route):
        nonlocal saved, batch, current_items
        request = route.request
        path = request.url.split('8766')[1].split('?')[0]
        calls.append((request.method, path))
        value = {}
        if path == '/api/startup/current':
            value = saved or {'generation': 0, 'state': None}
        elif path == '/api/startup/history':
            value = {'items': [saved] if saved else [], 'next_offset': None}
        elif path == '/api/startup/chat/conversations':
            value = {'items': [dict(id=cid, title='合成验收对话', version=len(turns))] if turns else [], 'next_offset': None}
        elif path.endswith('/conversations/' + cid):
            value = {'id': cid, 'version': len(turns), 'items': turns, 'next_before': None}
        elif path == '/api/startup/chat/messages':
            data = request.post_data_json
            ready = bool(turns)
            value = dict(id=str(len(turns)+3), conversation_id=cid, sequence=len(turns)+1,
                         base_generation=0, message=data['message'], status='succeeded', created_at=stamp,
                         response=dict(reply='建议压力80，能量70，可以修改。' if ready else '现在精力怎么样？', ready=ready,
                                       pressure=80 if ready else None, energy=70 if ready else None,
                                       difficulty='事情多', barrier='不知先做什么', goal='先做一件小事'))
            turns.append(value)
        elif path == '/api/startup/states':
            data = request.post_data_json
            assert data['confirmed'] and data['source_turn_id'] == '4'
            saved = dict(snapshot_id=sid, generation=1, pressure=data['pressure'], energy=data['energy'], difficulty=data['difficulty'], quadrant='降噪区', created_at=stamp, source_turn_id='4')
            value = saved
        elif path == '/api/startup/refresh':
            assert saved and request.post_data_json['expected_snapshot_id'] == sid
            if refresh_fails:
                route.fulfill(status=503, json={'error': '测试：模型暂不可用'})
                return
            if partial_mode:
                target = request.post_data_json.get('target_key')
                if target:
                    retry_targets.append(target)
                    batch = 'recovered-test-batch'
                    current_items = [item, dict(item, key=target, title='阅读资料', keyword='打开文档',
                        href='/tasks/example2', quadrants=['降噪区'], level='white', analysis_status='analyzed')]
                else:
                    batch = 'partial-test-batch'
                    current_items = [item, dict(item, key='task:example2', keyword='打开文档',
                        href='/tasks/example2', quadrants=[], level=None, analysis_status='pending',
                        analysis_id=None, error_code='upstream_timeout', reason='模型响应超时')]
            else:
                batch = 'shared-test-batch'
                current_items = [item]
            value = {'batch_id': batch, 'items': current_items, 'message':
                     '已分析 1 项，待分析 1 项' if partial_mode and not retry_targets else '推荐已更新'}
        elif path == '/api/startup/recommendations':
            value = {'batch_id': batch, 'items': current_items, 'message':
                     '已分析 1 项，待分析 1 项' if partial_mode and not retry_targets else '确认后刷新推荐'}
        else:
            raise AssertionError('Unexpected API: ' + path)
        route.fulfill(json=value)

    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        assert server.started
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.route('**/api/startup/**', respond)
            page.goto('http://127.0.0.1:8766/startup')
            expect(page.locator('#chat-input')).to_be_enabled()
            expect(page.locator('#recommend-refresh')).to_be_disabled()
            expect(page.locator('#chat-more')).to_be_hidden()
            expect(page.locator('#chat-more-conversations')).to_be_hidden()
            page.locator('#chat-input').fill('事情很多。')
            page.locator('#chat-form button').click()
            expect(page.locator('.chat-answer')).to_contain_text('现在精力怎么样')
            assert saved is None
            expect(page.get_by_role('button', name='载入建议，调整后确认')).to_have_count(0)
            page.locator('#chat-input').fill('压力80，能量70。')
            page.locator('#chat-form button').click()
            page.get_by_role('button', name='载入建议，调整后确认').click()
            expect(page.locator('#pressure')).to_have_value('80')
            expect(page.locator('#recommend-refresh')).to_be_disabled()
            page.locator('#pressure').press('ArrowLeft')
            page.get_by_role('button', name='确认并保存状态', exact=True).click()
            expect(page.locator('#recommend-refresh')).to_be_enabled()
            assert saved['pressure'] == 79
            page.locator('#recommend-refresh').click()
            expect(page.locator('#chat-top-tasks a')).to_have_text('整理一支笔')
            expect(page.locator('#chat-top-tasks')).to_have_attribute('data-batch-id', batch)
            expect(page.locator('#task-scatter a')).to_have_count(1)
            marker = page.locator('#task-scatter a').first
            expect(marker).to_have_attribute('href', '/tasks/example')
            marker.hover()
            expect(page.locator('#scatter-detail')).to_contain_text('整理桌面')
            expect(page.locator('#scatter-detail')).to_contain_text('先整理一支笔')
            expect(page.locator('#scatter-detail')).to_contain_text('让工作区更清爽')
            expect(page.locator('#scatter-detail')).to_contain_text('适合起步')
            partial_mode = True
            page.locator('#recommend-refresh').click()
            expect(page.get_by_role('button', name='单独重试')).to_have_count(1)
            expect(page.locator('#task-scatter a')).to_have_count(1)
            expect(page.locator('#recommend-list h3').last).to_have_text('待确认')
            expect(page.locator('#recommend-list section').last).to_contain_text('打开文档')
            page.get_by_role('button', name='单独重试').click()
            expect(page.get_by_role('button', name='单独重试')).to_have_count(0)
            expect(page.locator('#task-scatter a')).to_have_count(2)
            assert retry_targets == ['task:example2']
            refresh_fails = True
            page.locator('#recommend-refresh').click()
            expect(page.locator('#recommend-message')).to_contain_text('测试：模型暂不可用')
            expect(page.locator('#chat-top-tasks a')).to_have_text('整理一支笔')
            page.reload()
            expect(page.locator('#task-scatter a')).to_have_count(2)
            expect(page.locator('#chat-messages .chat-turn')).to_have_count(2)
            expect(page.locator('#pressure')).to_have_value('79')
            expect(page.locator('#chat-more')).to_be_hidden()
            original_items = current_items
            current_items = [dict(item, key=f'task:overlap{i}', title=f'任务{i}', href=f'/tasks/overlap{i}')
                             for i in range(10)]
            page.reload()
            markers = page.locator('#task-scatter a')
            expect(markers).to_have_count(10)
            positions = markers.evaluate_all('(nodes) => nodes.map(n => n.style.left + "," + n.style.top)')
            assert len(set(positions)) == 10, positions
            assert page.locator('#state-dot').get_attribute('cx') == '79'
            current_items = original_items + [dict(item, key='quest:example', kind='quest',
                title='让工作区更清爽', description='完成桌面整理', main_quest='让工作区更清爽',
                href='/quests/example', quadrants=['投入区'])]
            page.reload()
            expect(page.locator('#task-scatter a')).to_have_count(3)
            expect(page.locator('.task-marker-quest')).to_have_count(1)
            page.locator('.task-marker-quest').click()
            assert page.url.endswith('/quests/example')
            page.go_back()
            current_items = original_items
            page.reload()
            out = Path(tempfile.gettempdir()) / 'adventure-step7-verification'
            out.mkdir(exist_ok=True)
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(out/'desktop-final.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            page.evaluate('window.scrollTo(0,0)')
            expect(page.locator('#sidebar')).to_be_hidden()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.locator('#task-scatter a').first.focus()
            expect(page.locator('#scatter-detail')).to_contain_text('推荐理由')
            page.screenshot(path=str(out/'mobile-final.png'), full_page=True)
            page.locator('#theme-toggle').click()
            expect(page.locator('html')).to_have_attribute('data-theme','light')
            page.screenshot(path=str(out/'mobile-light.png'), full_page=True)
            assert not errors, errors
            assert len([c for c in calls if c == ('POST', '/api/startup/chat/messages')]) == 2
            browser.close()
            print('PASS: follow-up, advice, manual edit, confirmation gate, shared recommendation, failure, history, hidden controls, 390px, light/dark; synthetic HTTP fixtures.')
    finally:
        server.should_exit = True
        thread.join(timeout=10)


if __name__ == '__main__':
    run()
