from datetime import datetime, timedelta, timezone
import json
import os
import socket
import threading
import time
from uuid import uuid4

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import load_settings, postgres_url
from app.main import PAGES
from app.modules.ai_gateway.models import AICallLog, AIConfig
from app.modules.ai_gateway.service import AIService
from app.modules.artifact_spirit.catalog import BY_KEY
from app.modules.artifact_spirit.models import FeatureVisit
from test_distractions_postgres import notes, task_engine

BASE = '/api/artifact-spirit'
H = {'Origin': 'http://testserver'}


def test_catalog_matches_navigation():
    assert set(BY_KEY) == set(PAGES)
    for key, item in BY_KEY.items():
        assert item.title == PAGES[key]['title']
        assert set(item.related) <= BY_KEY.keys()


@pytest.mark.integration
def test_usage_and_browser(notes, monkeypatch):
    client, sessions, uid, other, app = notes
    assert client.get(BASE + '/usage').json()['candidates'] == []
    assert client.post(BASE + '/remind', headers=H, json={'request_id': str(uuid4())}).json()['suggestions'] == []
    assert client.post(BASE + '/visit', headers=H, json={'feature':'unknown'}).status_code == 422
    with sessions.begin() as db:
        old = datetime.now(timezone.utc) - timedelta(days=31)
        db.add(FeatureVisit(user_id=uid, feature='tasks', visited_at=old))
    assert client.post(BASE + '/visit', headers=H, json={'feature': 'tasks'}).json()['counted']
    assert not client.post(BASE + '/visit', headers=H, json={'feature': 'tasks'}).json()['counted']
    task = next(row for row in client.get(BASE + '/usage').json()['items'] if row['feature'] == 'tasks')
    assert (task['total'], task['recent']) == (2, 1)
    client.cookies.set('camp_session', str(other))
    assert sum(row['total'] for row in client.get(BASE + '/usage').json()['items']) == 0
    client.cookies.set('camp_session', str(uid))
    calls = []

    def generate(self, uid, purpose, messages, request_id, **kwargs):
        payload = json.loads(messages[-1]['content'])
        calls.append((purpose, payload))
        if purpose.endswith('_remind'):
            feature = payload[0]['feature']
            return {'content': {'summary': '或许可以回看近期记录', 'suggestions': [{
                'feature': feature, 'observation': '最近较少打开', 'action': '挑一条记录回看'
            }]}}
        return {'content': {'answer': '可以在副本任务里查看可执行步骤。', 'features': ['tasks']}}

    monkeypatch.setattr(AIService, 'generate', generate)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        origin = f'http://127.0.0.1:{sock.getsockname()[1]}'
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(.05)
            assert server.started
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel='msedge', headless=True)
                page = browser.new_page(viewport={'width': 1366, 'height': 900})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.context.add_cookies([{'name': 'camp_session', 'value': str(uid), 'url': origin}])
                page.goto(origin + '/artifact-spirit')
                expect(page.locator('[data-spirit-feature="artifact-spirit"] [data-spirit-count]')).to_contain_text('累计 1 次')
                card = page.locator('[data-spirit-feature="tasks"]')
                card.get_by_text('详情', exact=True).click()
                expect(card.get_by_text('已上线的变化')).to_be_visible()
                expect(card.get_by_role('link', name='专注沙漏')).to_have_attribute('href', '/focus')
                page.get_by_role('button', name='生成使用提醒').click()
                expect(page.locator('#spirit-summary')).to_have_text('或许可以回看近期记录')
                expect(page.locator('#spirit-reminders a')).to_have_count(1)
                page.get_by_role('button', name='向器灵提问').click()
                for text in ('副本任务有什么用？', '刚才说的功能和专注有什么关系？'):
                    page.get_by_label('你的问题').fill(text)
                    page.get_by_role('button', name='发送', exact=True).click()
                    expect(page.get_by_text('你：' + text, exact=True)).to_be_visible()
                assert calls[-1][1]['history'][0]['question'] == '副本任务有什么用？'
                expect(page.locator('#spirit-transcript a').first).to_have_attribute('href', '/tasks')
                page.reload()
                expect(page.locator('#spirit-transcript')).to_be_empty()
                expect(page.locator('[data-spirit-feature="artifact-spirit"] [data-spirit-count]')).to_contain_text('累计 1 次')
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors
                browser.close()
        finally:
            server.should_exit = True
            thread.join(10)


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('LIFE_OS_LIVE') != '1', reason='真实模型未显式启用')
def test_real_artifact_spirit(notes, monkeypatch):
    client, sessions, uid, _, app = notes
    settings = load_settings()
    engine = create_engine(postgres_url(settings.database_url.get_secret_value()), hide_parameters=True)
    try:
        with Session(engine) as db:
            config = db.scalar(select(AIConfig).where(AIConfig.is_default.is_(True),
                AIConfig.enabled.is_(True), AIConfig.deleted_at.is_(None)).limit(1))
            assert config
            values = {key: getattr(config, key) for key in (
                'base_url', 'model_id', 'protocol', 'encrypted_key', 'key_version', 'key_mask',
            )}
    finally:
        engine.dispose()
    with sessions.begin() as db:
        db.add(AIConfig(user_id=uid, create_request_id=uuid4(), create_fingerprint='test',
                        name='真实模型合成验收', is_default=True, **values))
    monkeypatch.undo()
    app.state.settings = settings
    assert client.post(BASE + '/visit', headers=H, json={'feature':'tasks'}).status_code == 200
    remind = client.post(BASE + '/remind', headers=H, json={'request_id': str(uuid4())})
    assert remind.status_code == 200, remind.text
    assert remind.json()['suggestions']
    reply = client.post(BASE + '/ask', headers=H, json={
        'request_id': str(uuid4()), 'question': '想记录真实的专注时长，结束后去哪里回看？请附对应的功能入口。'
    })
    assert reply.status_code == 200, reply.text
    assert 'journal' in reply.json()['features'], reply.text
    with sessions() as db:
        logs = db.scalars(select(AICallLog).where(AICallLog.user_id == uid)).all()
        assert len(logs) == 2 and all(log.status == 'succeeded' for log in logs)
        print('ARTIFACT_SPIRIT_LIVE_USAGE', {log.purpose: log.usage for log in logs})
