import json
import os
import socket
import threading
import time
from uuid import UUID, uuid4

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.core.config import load_settings, postgres_url
from app.modules.ai_gateway.models import AIConfig
from app.modules.ai_gateway.security import AIError
from app.modules.ai_gateway.service import AIService
from app.modules.shining_memories.people.models import MemoryPerson, MemoryPersonEvent
from test_distractions_postgres import notes, task_engine

pytestmark = pytest.mark.integration
BASE = '/api/shining-memories/friends'
MAP = BASE + '-map'
H = {'Origin': 'http://testserver'}


@pytest.fixture
def friend_case(notes):
    client, sessions, uid, _, _ = notes
    data = {'name': '合成朋友', 'relationship': '学习搭子', 'base_location': '上海',
            'precious_moments': '他答应每周陪练，连续三个月都准时参加。交流时他能准确复述我对音乐创作的想法。我觉得被支持，也更有信心继续练习。'}
    assert client.post(BASE, headers=H, json={**data, 'base_location': '  ',
                       'request_id': str(uuid4())}).status_code == 422
    response = client.post(BASE, headers=H, json={**data, 'request_id': str(uuid4())})
    assert response.status_code == 200, response.text
    person = response.json()
    yield notes, data, person
    # The shared fixture also checks downgrade. Remove only disposable friend rows.
    with sessions.begin() as db:
        db.execute(delete(MemoryPersonEvent).where(MemoryPersonEvent.user_id == uid,
                                                   MemoryPersonEvent.person_id == UUID(person['id'])))
        db.execute(delete(MemoryPerson).where(MemoryPerson.id == UUID(person['id'])))


def rerun(client, person, **extra):
    return client.post(MAP + '/' + person['id'], headers=H, json={
        'request_id': str(uuid4()), 'expected_version': person['version'],
        'consent_external': True, **extra,
    })


def test_friend_relationship_browser_and_persistence(friend_case, monkeypatch):
    (client, sessions, uid, other, app), data, person = friend_case
    with sessions.begin() as db:
        db.add(AIConfig(user_id=uid, create_request_id=uuid4(), create_fingerprint='test',
                        name='模拟模型', base_url='https://example.com/v1', model_id='synthetic',
                        protocol='openai_compatible', encrypted_key='unused', key_version=1,
                        key_mask='****', is_default=True))
    calls = []

    def generate(self, uid, purpose, messages, request_id, **kwargs):
        calls.append(purpose)
        sources = json.loads(messages[1]['content'])
        assert '上海' not in sources['moments'] and '合成朋友' not in sources['moments']
        evidence = dict(source='moments', quote='连续三个月都准时参加', reason='持续履行约定')
        return {'content': {'layers': [dict(evidence, layer=layer) for layer in (1, 4, 2, 3)],
                            'trust': dict(evidence, score=80), 'resonance': dict(evidence, score=70),
                            'text_impact': dict(evidence, score=80)}}

    monkeypatch.setattr(AIService, 'generate', generate)
    assert client.get('/api/shining-memories/people/' + person['id']).status_code == 404
    assert not client.get('/api/shining-memories/people').json()['items']
    assert rerun(client, person, consent_external=False).status_code == 403
    assert not calls

    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(.05)
            assert server.started
            origin = f'http://127.0.0.1:{port}'
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel='msedge', headless=True)
                page = browser.new_page(viewport={'width': 1366, 'height': 920})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('dialog', lambda dialog: dialog.accept())
                page.context.add_cookies([{'name': 'camp_session', 'value': str(uid), 'url': origin}])
                page.goto(origin + '/shining-memories/friends')
                expect(page.locator('.memory-tab')).to_have_text(['精神导师', '朋友搭子', '武器工坊', '心愿单'])
                expect(page.locator('#people-list')).to_contain_text('上海')
                expect(page.locator('#people-list')).to_contain_text('幸运值：待评估')
                expect(page.locator('.memory-friend-dot')).to_have_count(0)
                assert not calls
                page.get_by_role('button', name='重新读取').click()
                expect(page.locator('#friend-map-status')).to_contain_text('读取完成 1/1', timeout=20000)
                expect(page.locator('#people-list')).to_contain_text('幸运值：77/100')
                expect(page.locator('[data-friend-layer="4"] button')).to_have_attribute('title', '合成朋友')
                expect(page.locator('.memory-friend-layer-dots button')).to_have_count(1)
                axis = page.locator('.memory-friend-axis-y')
                expect(axis.locator('span').first).to_have_text('↑')
                expect(axis).to_have_css('transform', 'none')
                expect(axis.locator('.memory-friend-axis-y-label')).to_have_css('text-orientation', 'upright')
                page.locator('#friend-quadrant-points button').click()
                expect(page.locator('#friend-map-selection')).to_contain_text('可信度 80')
                expect(page.locator('#person-detail')).to_contain_text('上海')
                expect(page.locator('#person-detail')).to_contain_text('幸运值：77/100')
                page.reload()
                expect(page.locator('.memory-friend-dot')).to_have_count(2)
                page.get_by_role('button', name='重新读取').click()
                expect(page.locator('#friend-map-status')).to_contain_text('复用 1', timeout=20000)
                assert calls == ['friend_relationship']
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors
                browser.close()
        finally:
            server.should_exit = True
            thread.join(10)

    url = BASE + '/' + person['id']
    edited = client.patch(url, headers=H, json={**data, 'expected_version': 1,
                                               'notes': '新增经历，待重新分析'}).json()
    assert client.get(MAP).json()['items'][0]['stale']
    event_response = client.post(url + '/events', headers=H, json={
        'request_id': str(uuid4()), 'event_date': '2026-01-02',
        'content': '记录一次合成学习聚会', 'is_actual_contact': True,
    })
    assert event_response.status_code == 200
    event = event_response.json()
    changed = client.patch(url + '/events/' + event['id'], headers=H, json={
        'expected_version': event['version'], 'event_date': '2026-01-03',
        'content': '记录一次合成交流', 'is_actual_contact': True,
    })
    assert changed.status_code == 200
    assert client.get(url + '/events').json()['items'][0]['content'] == '记录一次合成交流'
    assert client.get('/api/shining-memories/people/' + person['id'] + '/events').status_code == 404
    edited = client.get(url).json()

    def timeout(*args, **kwargs):
        raise AIError('upstream_timeout', '模型超时', 504)
    monkeypatch.setattr(AIService, 'generate', timeout)
    assert rerun(client, edited).status_code == 504
    assert client.get(MAP).json()['items'][0]['mapping']['trust']['score'] == 80
    # Newer unscored and lower-scored records still sort after the original friend.
    with sessions.begin() as db:
        for name, score in [('合成待评估', None), ('合成低分', 10)]:
            saved = None if score is None else {'version': 1, 'result': {
                'layers': [{'layer': 1}], 'trust': {'score': score},
                'resonance': {'score': score}, 'text_impact': {'score': score},
            }}
            db.add(MemoryPerson(user_id=uid, kind='friend', base_location='北京',
                name=name, relationship='合成关系', create_request_id=uuid4(),
                create_fingerprint='test', friend_mapping=saved))
    try:
        assert [item['luck_score'] for item in client.get(BASE).json()['items']] == [77, 11, None]
        assert client.get(BASE).json()['items'][0]['luck_stale']
    finally:
        with sessions.begin() as db:
            db.execute(delete(MemoryPerson).where(MemoryPerson.user_id == uid,
                MemoryPerson.name.in_(['合成待评估', '合成低分'])))
    client.cookies.set('camp_session', str(other))
    assert client.get(MAP).json()['items'] == []
    assert client.get(url).status_code == 404
    assert rerun(client, edited).status_code == 404
    client.cookies.set('camp_session', str(uid))
    assert client.request('DELETE', url, headers=H, json={'expected_version': edited['version']}).status_code == 200
    assert client.get(MAP).json()['items'] == []


@pytest.mark.skipif(os.getenv('LIFE_OS_LIVE') != '1', reason='真实模型未显式启用')
def test_friend_relationship_real_model(friend_case, monkeypatch):
    (client, sessions, uid, _, app), _, person = friend_case
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
    response = rerun(client, person)
    assert response.status_code == 200, response.text
    result = response.json()['mapping']
    assert result['layers'] and result['trust'] and result['resonance']
    assert result['text_impact'] and response.json()['luck_score'] is not None
    assert rerun(client, person).json()['cached']
    from app.modules.ai_gateway.models import AICallLog
    with sessions() as db:
        log = db.scalar(select(AICallLog).where(AICallLog.user_id == uid,
                                              AICallLog.purpose == 'friend_relationship'))
        print('FRIEND_LIVE_USAGE', log.usage)
