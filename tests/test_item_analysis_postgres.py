import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select
from app.modules.ai_gateway.security import AIError
from app.modules.startup_items import analysis
from app.modules.startup_items.models import StartupItem
from test_ai_postgres import ai, make, task_engine, camp

pytestmark = pytest.mark.integration
HEADERS = {'Origin': 'http://testserver'}


def create(client, description):
    response = client.post('/api/startup/items', headers=HEADERS, json={
        'description': description, 'importance': 85, 'urgency': 80, 'progress': '尚未开始', 'request_id': str(uuid4())})
    assert response.status_code == 200, response.text
    return response.json()


def run(client, item, request_id=None):
    return client.post('/api/startup/items/' + item['id'] + '/analyze', headers=HEADERS,
        json={'request_id': str(request_id or uuid4())})


def answer(item_id, **extra):
    return analysis.Classification(item_id=item_id, keyword='打开文档', quadrant='投入区',
        reason='需要较完整的精力进行思考', action='先打开文件，只读一段', **extra)


def test_partial_cache_edit_failure_old_result_and_state_independence(ai, monkeypatch):
    camp, _, _, client = ai
    make(ai)
    first, second = create(client, '完善代码'), create(client, '整理桌面')
    calls = []
    fail = True

    def provider(self, uid, purpose, messages, request_id, schema, **kwargs):
        assert camp['engine'].pool.checkedout() == 0
        payload = json.loads(messages[-1]['content'])
        assert set(payload) == {'item_id', 'item'}
        assert set(payload['item']) == {'description', 'importance', 'urgency', 'progress'}
        calls.append(payload['item_id'])
        if fail and payload['item_id'] == second['id']:
            raise AIError('upstream_timeout', 'safe timeout', 504)
        return {'content': answer(payload['item_id'])}

    monkeypatch.setattr(analysis.AIService, 'generate', provider)
    assert run(client, first).json()['item']['analysis']['status'] == 'analyzed'
    failed = run(client, second).json()['item']['analysis']
    assert failed['status'] == 'failed' and failed['error_code'] == 'upstream_timeout'
    assert client.get('/api/startup/items/' + first['id']).json()['analysis']['result']['quadrant'] == '投入区'
    assert run(client, first).json()['cached'] and len(calls) == 2
    state = client.post('/api/startup/states', headers=HEADERS, json={'pressure': 80, 'energy': 20,
        'confirmed': True, 'expected_generation': 0, 'request_id': str(uuid4())})
    assert state.status_code == 200
    assert run(client, first).json()['cached'] and len(calls) == 2
    fail = False
    assert run(client, second).json()['item']['analysis']['status'] == 'analyzed'
    url = '/api/startup/items/' + second['id']
    edited = client.patch(url, headers=HEADERS, json={
        'description': '只移动一支笔', 'importance': 35, 'urgency': 30, 'progress': '已经完成一半', 'expected_version': 1}).json()
    assert edited['analysis']['status'] == 'stale' and edited['analysis']['previous_result']
    fail = True
    after = run(client, second).json()['item']['analysis']
    assert after['status'] == 'failed' and after['result'] is None and after['previous_result']
    assert len(calls) == 4
    with camp['sessions']() as db:
        row = db.get(StartupItem, UUID(first['id']))
        assert row.analysis_result['item_id'] == first['id'] and row.version == 1


def test_no_model_wrong_id_empty_classification_and_permissions(ai, monkeypatch):
    camp, _, _, client = ai
    item = create(client, '可能要处理一件事')
    assert run(client, item).json()['item']['analysis']['error_code'] == 'no_model'
    make(ai)
    monkeypatch.setattr(analysis.AIService, 'generate', lambda *a, **kw: {'content': answer(uuid4())})
    request_id = uuid4()
    assert run(client, item, request_id).json()['item']['analysis']['error_code'] == 'invalid_schema'
    assert run(client, item, request_id).json()['replayed']
    monkeypatch.setattr(analysis.AIService, 'generate', lambda *a, **kw: {'content': {
        'item_id': item['id'], 'keyword': '待澄清', 'quadrant': None,
        'reason': '没有说明事情是什么', 'action': '先补充具体要做什么'}})
    unknown = run(client, item).json()['item']['analysis']
    assert unknown['status'] == 'unclassified' and unknown['result']['quadrant'] is None
    assert run(client, item).json()['cached']
    assert client.post('/api/startup/items/' + str(uuid4()) + '/analyze', headers=HEADERS,
        json={'request_id': str(uuid4())}).status_code == 404
    with pytest.raises(AIError):
        analysis.analyze(ai[2].state.database, ai[1], camp['other'], UUID(item['id']), uuid4())
    client.cookies.clear()
    assert run(client, item).status_code == 401


def test_edit_during_analysis_does_not_publish_stale_coordinates(ai, monkeypatch):
    camp, settings, app, client = ai
    make(ai)
    item = create(client, '阅读一篇文章')
    entered, release = Event(), Event()
    def provider(*args, **kwargs):
        entered.set()
        assert release.wait(30)
        return {'content': answer(item['id'])}
    monkeypatch.setattr(analysis.AIService, 'generate', provider)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(analysis.analyze, app.state.database, settings, camp['user'], UUID(item['id']), uuid4())
        try:
            assert entered.wait(20)
            changed = client.patch('/api/startup/items/' + item['id'], headers=HEADERS,
                json={'description': '改为整理桌面', 'importance': 40, 'urgency': 20, 'progress': '', 'expected_version': 1})
            assert changed.status_code == 200
        finally:
            release.set()
        value = future.result(timeout=30)['item']['analysis']
    assert value['result'] is None
    with camp['sessions']() as db:
        assert db.get(StartupItem, UUID(item['id'])).analysis_result is None
