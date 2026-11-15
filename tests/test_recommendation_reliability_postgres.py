"""Real PostgreSQL checks for independent analysis, retries and snapshot matching."""
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.modules.ai_gateway.security import AIError
from app.modules.startup_state.models import StateCurrent
from app.modules.task_recommendation import service as recommendation
from app.modules.task_recommendation.models import RecommendationBatch, TaskAnalysis
from app.modules.tasks import service as tasks
from app.modules.tasks.models import Task
from test_ai_postgres import ai, make, task_engine, camp

pytestmark = pytest.mark.integration
HEADERS = {'Origin': 'http://testserver'}


def add_task(camp, title, description):
    with camp['sessions'].begin() as db:
        return tasks.execute(db, camp['user'], uuid4(), 'create',
                             {'title': title, 'description': description})


def refresh(client, snapshot_id, target_key=None):
    return client.post('/api/startup/refresh', headers=HEADERS,
                       json={'request_id': str(uuid4()), 'expected_snapshot_id': snapshot_id,
                             'target_key': target_key})


def test_partial_retry_cache_state_and_persistence(ai, monkeypatch):
    camp, _, _, client = ai
    make(ai)
    first = add_task(camp, '读一页书', '只读第一段')
    second = add_task(camp, '整理桌面', '将一支笔放进笔筒')
    calls = []
    fail_second = True

    def provider(self, uid, purpose, messages, request_id, output_schema=None, **kwargs):
        nonlocal fail_second
        assert purpose == 'task_analysis'
        title = __import__('json').loads(messages[-1]['content'])['title']
        calls.append(title)
        if title == '整理桌面' and fail_second:
            raise AIError('upstream_timeout', 'safe timeout', 504)
        return {'content': recommendation.Features(keyword=title, quadrants=['投入区'],
                effort=3, barrier=3, clear_next=True, reason='可以先做一步')}

    monkeypatch.setattr(recommendation.AIService, 'generate', provider)
    saved = client.post('/api/startup/states', headers=HEADERS, json={
        'pressure': 10, 'energy': 90, 'difficulty': '', 'confirmed': True,
        'expected_generation': 0, 'request_id': str(uuid4())})
    assert saved.status_code == 200, saved.text
    sid = saved.json()['snapshot_id']
    partial = refresh(client, sid)
    assert partial.status_code == 200, partial.text
    body = partial.json()
    assert body['status'] == 'partial' and body['summary'] == {'analyzed': 1, 'pending': 2, 'stale': 0}
    assert len(calls) == 2  # Empty-description quest uses no model.
    analyzed = next(x for x in body['items'] if x['key'] == 'task:' + str(first))
    pending = next(x for x in body['items'] if x['key'] == 'task:' + str(second))
    assert analyzed['level'] == 'green' and pending['level'] is None
    assert analyzed['kind'] == 'task' and analyzed['title'] == '读一页书'
    assert analyzed['description'] == '只读第一段' and analyzed['main_quest'] == '独立副本'
    assert analyzed['href'] == '/tasks/' + str(first)
    assert pending['title'] == '整理桌面' and pending['description'] == '将一支笔放进笔筒'
    assert pending['analysis_status'] == 'pending' and pending['error_code'] == 'upstream_timeout'
    assert client.get('/api/startup/recommendations').json()['batch_id'] == body['batch_id']
    with camp['sessions']() as db:
        assert len(list(db.scalars(select(TaskAnalysis).where(TaskAnalysis.user_id == camp['user'])))) == 1
        assert db.get(RecommendationBatch, UUID(body['batch_id'])).snapshot_id == UUID(sid)

    fail_second = False
    retried = refresh(client, sid, 'task:' + str(second))
    assert retried.status_code == 200, retried.text
    assert retried.json()['summary']['analyzed'] == 2
    assert calls == ['读一页书', '整理桌面', '整理桌面']
    assert refresh(client, sid).json()['summary']['analyzed'] == 2
    assert len(calls) == 3

    current = client.get('/api/startup/current').json()
    changed = client.post('/api/startup/states', headers=HEADERS, json={
        'pressure': 90, 'energy': 10, 'difficulty': '', 'confirmed': True,
        'expected_generation': current['generation'], 'request_id': str(uuid4())})
    assert changed.status_code == 200, changed.text
    new_sid = changed.json()['snapshot_id']
    recolored = refresh(client, new_sid)
    assert recolored.status_code == 200, recolored.text
    assert len(calls) == 3
    assert next(x for x in recolored.json()['items'] if x['key'] == 'task:' + str(first))['level'] == 'red'
    assert client.get('/api/startup/recommendations').json()['batch_id'] == recolored.json()['batch_id']

    with camp['sessions'].begin() as db:
        task = db.get(Task, first)
        tasks.execute(db, camp['user'], uuid4(), 'edit', {'title': '读一页书', 'description': '只读第二段'},
                      [first], {str(first): task.version})
    assert refresh(client, new_sid).status_code == 200
    assert calls[-1] == '读一页书' and len(calls) == 4


def test_systemic_failure_preserves_last_batch(ai, monkeypatch):
    camp, _, _, client = ai
    make(ai)
    add_task(camp, '一步任务', '打开文档')
    monkeypatch.setattr(recommendation.AIService, 'generate',
                        lambda *a, **kw: {'content': recommendation.Features(
                            keyword='打开文档', quadrants=['投入区'], effort=1,
                            barrier=1, clear_next=True, reason='一步即可')})
    state = client.post('/api/startup/states', headers=HEADERS, json={
        'pressure': 20, 'energy': 80, 'confirmed': True,
        'expected_generation': 0, 'request_id': str(uuid4())}).json()
    first = refresh(client, state['snapshot_id']).json()
    original = recommendation.config_signature
    count = 0

    def fail_late(db, uid):
        nonlocal count
        count += 1
        if count > 1:
            raise AIError('stale', 'changed', 409)
        return original(db, uid)

    monkeypatch.setattr(recommendation, 'config_signature', fail_late)
    failed = refresh(client, state['snapshot_id'])
    assert failed.status_code == 409
    monkeypatch.setattr(recommendation, 'config_signature', original)
    view = client.get('/api/startup/recommendations').json()
    assert view['batch_id'] == first['batch_id'] and len(view['items']) == 2
    with camp['sessions']() as db:
        latest = db.scalar(select(RecommendationBatch).where(RecommendationBatch.user_id == camp['user'])
                           .order_by(RecommendationBatch.created_at.desc(), RecommendationBatch.id.desc()))
        assert latest.status == 'failed' and latest.error_code == 'stale'
