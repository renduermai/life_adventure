from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select
from app.core.config import Settings
from app.main import create_app
from app.modules.distractions import service
from app.modules.distractions.models import DistractionNote
from app.modules.distractions.schemas import Create
from app.modules.identity.models import User, LoginSession
from app.modules.identity.service import token_hash
from app.modules.ai_gateway.service import AIService
from test_tasks_postgres import task_engine

pytestmark = pytest.mark.integration
HEADERS = {'Origin': 'http://testserver'}
BASE = '/api/distractions/notes'


@pytest.fixture
def notes(task_engine, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    sessions = sessionmaker(task_engine, expire_on_commit=False)
    owner, other = uuid4(), uuid4()
    with sessions.begin() as db:
        db.add_all([User(id=uid, username='notes_' + uid.hex, password_hash='unused',
            display_name='测试', timezone='Asia/Shanghai') for uid in (owner, other)])
        db.flush()
        db.add_all([LoginSession(user_id=uid, token_hash=token_hash(str(uid)),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1)) for uid in (owner, other)])
    def no_ai(*args, **kwargs):
        pytest.fail('原文接口不得调用 AI')
    monkeypatch.setattr(AIService, 'generate', no_ai)
    app = create_app(Settings(_env_file=None))
    @contextmanager
    def transaction():
        with sessions.begin() as db:
            yield db
    app.state.database.sessions = sessions
    app.state.database.transaction = transaction
    with TestClient(app) as client:
        client.cookies.set('camp_session', str(owner))
        yield client, sessions, owner, other, app


def test_original_idempotency_delete_and_new_app(notes):
    client, sessions, owner, other, app = notes
    content = '  担心能力不足。\n保留原文  '
    payload = dict(request_id=str(uuid4()), content=content)
    r = client.post(BASE, headers=HEADERS, json=payload)
    assert r.status_code == 200, r.text
    first = r.json()
    assert first['content'] == content and first['created_at']
    assert client.post(BASE, headers=HEADERS, json=payload).json()['id'] == first['id']
    assert client.post(BASE, headers=HEADERS, json=payload | {'content':'different'}).status_code == 409
    second = client.post(BASE, headers=HEADERS, json=payload | {'request_id':str(uuid4())}).json()
    url = BASE + '/' + first['id']
    # A fresh application and connection read committed originals, not process memory.
    app2 = create_app(Settings(_env_file=None))
    app2.state.database.sessions = sessions
    app2.state.database.transaction = app.state.database.transaction
    with TestClient(app2) as fresh:
        fresh.cookies.set('camp_session', str(owner))
        assert fresh.get(url).json()['content'] == content
    assert client.request('DELETE', url, headers=HEADERS, json={'expected_version':2}).status_code == 409
    client.cookies.set('camp_session', str(other))
    assert client.get(BASE).json()['items'] == []
    assert client.get(url).status_code == 404
    assert client.request('DELETE', url, headers=HEADERS, json={'expected_version':1}).status_code == 404
    client.cookies.set('camp_session', str(owner))
    assert client.request('DELETE', url, headers=HEADERS, json={'expected_version':1}).status_code == 200
    assert client.get(url).status_code == 404
    assert client.post(BASE, headers=HEADERS, json=payload).status_code == 409
    assert [n['id'] for n in client.get(BASE).json()['items']] == [second['id']]
    with sessions() as db:
        row = db.get(DistractionNote, UUID(first['id']))
        assert row.deleted_at and row.content == content and row.version == 2
        assert {fk['referred_table'] for fk in inspect(db.bind).get_foreign_keys('distraction_notes')} == {'users'}


def test_validation_auth_and_private_errors(notes, caplog):
    client, _, _, _, _ = notes
    secret = 'private-original-sentinel'
    for value in (' ', 'x'*5001, None, 123, 'a\x00b'):
        r = client.post(BASE, headers=HEADERS, json={'request_id':str(uuid4()), 'content':value})
        assert r.status_code == 422, r.text
    r = client.post(BASE, headers=HEADERS, json={'request_id':str(uuid4()), 'content':secret, 'task_id':str(uuid4())})
    assert r.status_code == 422 and secret not in r.text and secret not in caplog.text
    assert client.post(BASE, json={'request_id':str(uuid4()), 'content':'x'}).status_code == 403
    client.cookies.clear()
    assert client.get(BASE).status_code == 401
    assert client.post(BASE, headers=HEADERS, json={'request_id':str(uuid4()), 'content':'x'}).status_code == 401


def test_pagination_concurrency_and_rollback(notes):
    client, sessions, owner, _, _ = notes
    data = Create(request_id=uuid4(), content='same request')
    def save():
        with sessions.begin() as db:
            return service.create(db, owner, data)['id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert len(set(pool.map(lambda _: save(), range(2)))) == 1
    with pytest.raises(RuntimeError):
        with sessions.begin() as db:
            service.create(db, owner, Create(request_id=uuid4(), content='rollback'))
            raise RuntimeError('force rollback')
    with sessions.begin() as db:
        for _ in range(22):
            service.create(db, owner, Create(request_id=uuid4(), content='independent'))
        # Equal timestamps deliberately exercise the UUID tie-breaker.
    page1 = client.get(BASE).json()
    page2 = client.get(BASE, params={'offset':page1['next_offset']}).json()
    assert len(page1['items']) == 20 and len(page2['items']) == 3
    ids = [row['id'] for row in page1['items'] + page2['items']]
    assert len(set(ids)) == 23 and page2['next_offset'] is None
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(DistractionNote).where(DistractionNote.user_id == owner)) == 23
