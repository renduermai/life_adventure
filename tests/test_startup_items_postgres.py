from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import pytest
from sqlalchemy import func, inspect, select
from app.modules.identity.models import LoginSession
from app.modules.identity.service import token_hash
from app.modules.startup_items.models import StartupItem
from app.modules.tasks.models import Task
from app.modules.quests.models import MainQuest
from test_ai_postgres import ai, task_engine, camp

pytestmark = pytest.mark.integration
HEADERS = {'Origin': 'http://testserver'}


def fields(**extra):
    return dict(description='检查几个 Bug', importance=85, urgency=80, progress='已定位两个') | extra


def test_crud_persistence_soft_delete_and_isolation(ai):
    camp, _, _, client = ai
    payload = fields(request_id=str(uuid4()))
    created = client.post('/api/startup/items', headers=HEADERS, json=payload)
    assert created.status_code == 200, created.text
    item = created.json()
    assert client.post('/api/startup/items', headers=HEADERS, json=payload).json()['id'] == item['id']
    assert client.post('/api/startup/items', headers=HEADERS, json=payload | {'description': 'different'}).status_code == 409
    another = client.post('/api/startup/items', headers=HEADERS, json=fields(
        description='看看 AI 工具', progress='', importance=40, urgency=20, request_id=str(uuid4()))).json()
    url = '/api/startup/items/' + item['id']
    assert len(client.get('/api/startup/items').json()['items']) == 2
    updated = client.patch(url, headers=HEADERS, json=fields(description='修复已定位的 Bug',
        importance=100, urgency=0, progress='已经复现', expected_version=1))
    assert updated.status_code == 200, updated.text
    assert updated.json()['version'] == 2
    assert client.patch(url, headers=HEADERS, json=fields(expected_version=1)).status_code == 409
    assert client.request('DELETE', url, headers=HEADERS, json={'expected_version': 1}).status_code == 409
    with camp['sessions']() as db:
        row = db.get(StartupItem, UUID(item['id']))
        assert row.description == '修复已定位的 Bug' and row.progress == '已经复现'
        assert (row.importance, row.urgency, row.version) == (100, 0, 2)
        assert db.scalar(select(func.count()).select_from(Task).where(Task.user_id == camp['user'])) == 0
        assert db.get(MainQuest, camp['quest']).status == 'active'
        assert {fk['referred_table'] for fk in inspect(camp['engine']).get_foreign_keys('startup_items')} == {'users'}
    with camp['sessions'].begin() as db:
        db.add(LoginSession(user_id=camp['other'], token_hash=token_hash(str(camp['other'])),
            expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
    client.cookies.set('camp_session', str(camp['other']))
    assert client.get('/api/startup/items').json()['items'] == []
    assert client.get(url).status_code == 404
    assert client.patch(url, headers=HEADERS, json=fields(expected_version=2)).status_code == 404
    assert client.request('DELETE', url, headers=HEADERS, json={'expected_version': 2}).status_code == 404
    client.cookies.set('camp_session', str(camp['user']))
    assert client.request('DELETE', url, headers=HEADERS, json={'expected_version': 2}).status_code == 200
    assert client.get(url).status_code == 404
    assert [x['id'] for x in client.get('/api/startup/items').json()['items']] == [another['id']]
    with camp['sessions']() as db:
        assert db.get(StartupItem, UUID(item['id'])).deleted_at is not None


def test_validation_and_authentication(ai):
    _, _, _, client = ai
    for bad in ({'description': ' '}, {'importance': -1}, {'urgency': 101},
                {'importance': True}, {'urgency': 1.5}, {'main_quest_id': str(uuid4())}):
        response = client.post('/api/startup/items', headers=HEADERS,
            json=fields(request_id=str(uuid4())) | bad)
        assert response.status_code == 422, response.text
    assert client.post('/api/startup/items', json=fields(request_id=str(uuid4()))).status_code == 403
    client.cookies.clear()
    assert client.get('/api/startup/items').status_code == 401
    assert client.post('/api/startup/items', headers=HEADERS, json=fields(request_id=str(uuid4()))).status_code == 401
