from contextlib import contextmanager
from uuid import UUID, uuid4
import os
import pytest
from sqlalchemy import select, func
from app.modules.distractions import classification_service as cs, service
from app.modules.distractions.schemas import Create, Delete
from app.modules.distractions.models import DistractionNote, ClassificationRun
from app.modules.ai_gateway.security import AIError
from test_distractions_postgres import notes, task_engine

pytestmark=pytest.mark.integration


def test_version_cache_failure_and_counts(notes,monkeypatch):
    client,sessions,uid,other,app=notes
    cid=uuid4()
    monkeypatch.setattr(cs,'configuration',lambda db,user:(cid,1))
    calls=[]
    def generate(self,user,purpose,messages,request_id,**kwargs):
        import json
        units=json.loads(messages[-1]['content']);calls.append(units)
        return {'content':cs.Result(groups=[dict(category='求职焦虑',summary='担心能力不足',note_ids=[u['id'] for u in units])],unclassified_note_ids=[])}
    monkeypatch.setattr(cs.AIService,'generate',generate)
    for content in ['担心能力不足','怕不能胜任','担心能力不足']:
        with sessions.begin() as db: service.create(db,uid,Create(request_id=uuid4(),content=content))
    result=cs.classify(app.state.database,None,uid,uuid4())
    assert result['groups'][0]['count']==3 and not result['cached']
    assert cs.classify(app.state.database,None,uid,uuid4())['cached'] and len(calls)==1
    with sessions.begin() as db:
        assert cs.view(db,other)['groups']==[]
        first=db.scalar(select(DistractionNote).where(DistractionNote.user_id==uid))
        service.delete(db,uid,first.id,Delete(expected_version=1))
    with sessions.begin() as db: assert cs.view(db,uid)['groups'][0]['count']==2
    def timeout(*args,**kwargs): raise AIError('upstream_timeout','模型超时',504)
    monkeypatch.setattr(cs.AIService,'generate',timeout)
    with pytest.raises(AIError): cs.classify(app.state.database,None,uid,uuid4())
    with sessions.begin() as db:
        view=cs.view(db,uid)
        assert view['run_id']==result['run_id'] and view['groups'][0]['count']==2
        assert view['error_code']=='upstream_timeout'
    monkeypatch.setattr(cs.AIService,'generate',lambda *a,**k:{'content':cs.Result(groups=[],unclassified_note_ids=[uuid4()])})
    with pytest.raises(AIError,match='编号'): cs.classify(app.state.database,None,uid,uuid4())
    assert client.get('/api/distractions/notes/classification/current').json()['groups'][0]['count']==2
    topic=result['groups'][0]['id']; run=result['run_id']
    url=f'/api/distractions/notes/classification/{run}/entries'
    response=client.get(url,params={'kind':'topic','topic_id':str(topic)})
    assert response.status_code==200 and len(response.json()['items'])==2
    client.cookies.set('camp_session', str(other))
    assert client.get(url,params={'kind':'topic','topic_id':str(topic)}).status_code==409
    client.cookies.set('camp_session', str(uid))
    with sessions.begin() as db:
        remaining = list(db.scalars(select(DistractionNote).where(DistractionNote.user_id == uid, DistractionNote.deleted_at.is_(None))))
        for note in remaining:
            service.delete(db, uid, note.id, Delete(expected_version=note.version))
    assert client.get('/api/distractions/notes/classification/current').json()['groups'] == []



def test_batches_unclassified_and_snapshot_change(notes,monkeypatch):
    import json
    client,sessions,uid,_,app=notes
    monkeypatch.setattr(cs,'configuration',lambda db,user:(UUID(int=1),1))
    for index in range(21):
        with sessions.begin() as db: service.create(db,uid,Create(request_id=uuid4(),content='合成担忧'+str(index)))
    calls=[]
    def grouped(*args,**kwargs):
        units=json.loads(args[3][-1]['content']);calls.append(units)
        return {'content':cs.Result(groups=[dict(category='学习',summary='担心进度',note_ids=[u['id'] for u in units])],unclassified_note_ids=[])}
    monkeypatch.setattr(cs.AIService,'generate',grouped)
    result=cs.classify(app.state.database,None,uid,uuid4())
    assert len(calls)==3 and result['groups'][0]['count']==21
    with sessions.begin() as db: service.create(db,uid,Create(request_id=uuid4(),content='新的'))
    def changed(*args,**kwargs):
        with sessions.begin() as db: service.create(db,uid,Create(request_id=uuid4(),content='分析中新增'))
        return grouped(*args,**kwargs)
    monkeypatch.setattr(cs.AIService,'generate',changed)
    with pytest.raises(AIError,match='已变化'): cs.classify(app.state.database,None,uid,uuid4())
    with sessions.begin() as db:
        view=cs.view(db,uid)
        assert view['run_id']==result['run_id'] and len(view['pending_note_ids'])>0
    def unclassified(*args,**kwargs):
        units=json.loads(args[3][-1]['content'])
        return {'content':cs.Result(groups=[],unclassified_note_ids=[u['id'] for u in units])}
    monkeypatch.setattr(cs.AIService,'generate',unclassified)
    result=cs.classify(app.state.database,None,uid,uuid4())
    assert not result['groups'] and len(result['unclassified_note_ids'])==result['total']


def test_http_classification_history_restart_and_failures(notes, monkeypatch):
    import json
    from app.main import create_app
    from app.core.config import Settings
    from fastapi.testclient import TestClient
    from app.modules.distractions.models import ClassificationRun, DistractionMembership
    client, sessions, uid, other, app = notes
    monkeypatch.setattr(cs, 'configuration', lambda db, user: (UUID(int=1), 1))
    headers = {'Origin': 'http://testserver'}
    originals = [
        '  担心技术不够，无法胜任岗位。\n原文不修剪  ',
        '看到招聘要求很高，担心自己能力不足。',
        '担心学习进度跟不上计划。',
        '担心学习进度跟不上计划。',
    ]
    for content in originals:
        response = client.post('/api/distractions/notes', headers=headers,
            json={'request_id': str(uuid4()), 'content': content})
        assert response.status_code == 200, response.text
    seen = []
    def classify_reply(self, user, purpose, messages, request_id, **kwargs):
        units = json.loads(messages[-1]['content'])
        seen.append(len(units))
        return {'content': cs.Result(groups=[
            {'category':'未来规划', 'summary':'担心求职能力', 'note_ids':[x['id'] for x in units if '进度' not in x['text']]},
            {'category':'未来规划', 'summary':'担心学习进度', 'note_ids':[x['id'] for x in units if '进度' in x['text']]},
        ], unclassified_note_ids=[])}
    monkeypatch.setattr(cs.AIService, 'generate', classify_reply)
    endpoint = '/api/distractions/notes/classifications'
    first = client.post(endpoint, headers=headers, json={'request_id':str(uuid4())})
    assert first.status_code == 200, first.text
    result = first.json()
    assert seen == [4] and [group['count'] for group in result['groups']] == [2, 2]
    assert len({group['category'] for group in result['groups']}) == 1
    assert client.post(endpoint, headers=headers, json={'request_id':str(uuid4())}).json()['cached']
    assert seen == [4]
    run = result['run_id']
    group = next(g for g in result['groups'] if '求职' in g['summary'])
    detail_url = f'/api/distractions/notes/classification/{run}/entries'
    detail = client.get(detail_url, params={'kind':'topic','topic_id':group['id']})
    assert detail.status_code == 200
    assert {x['content'] for x in detail.json()['items']} == set(originals[:2])
    assert all(x['created_at'] for x in detail.json()['items'])

    from contextlib import contextmanager
    app2 = create_app(Settings(_env_file=None))
    app2.state.database.sessions = sessions
    @contextmanager
    def transaction():
        with sessions.begin() as db:
            yield db
    app2.state.database.transaction = transaction
    with TestClient(app2) as fresh:
        fresh.cookies.set('camp_session', str(uid))
        assert fresh.get('/api/distractions/notes/classification/current').json()['run_id'] == run
        assert len(fresh.get(detail_url, params={'kind':'topic','topic_id':group['id']}).json()['items']) == 2

    def fail(code):
        def generate(*args, **kwargs):
            raise AIError(code, '合成失败', 502)
        monkeypatch.setattr(cs.AIService, 'generate', generate)
        response = client.post(endpoint, headers=headers, json={'request_id':str(uuid4())})
        assert response.status_code == 502
        assert client.get('/api/distractions/notes/classification/current').json()['run_id'] == run
    added = client.post('/api/distractions/notes', headers=headers,
        json={'request_id':str(uuid4()), 'content':'待归类的新杂念'})
    assert added.status_code == 200
    current = client.get('/api/distractions/notes/classification/current').json()
    assert len(current['pending_note_ids']) == 1 and current['needs_reclassification']
    fail('invalid_json')
    fail('invalid_schema')
    fail('upstream_timeout')
    monkeypatch.setattr(cs.AIService, 'generate', classify_reply)
    from sqlalchemy.orm import Session
    from app.modules.distractions.models import DistractionTopic
    original_flush = Session.flush
    failed_once = {'value': False}
    def fail_topic_flush(self, *args, **kwargs):
        if not failed_once['value'] and any(isinstance(row, DistractionTopic) for row in self.new):
            failed_once['value'] = True
            raise RuntimeError('synthetic topic write failure')
        return original_flush(self, *args, **kwargs)
    monkeypatch.setattr(Session, 'flush', fail_topic_flush)
    response = client.post(endpoint, headers=headers, json={'request_id':str(uuid4())})
    assert response.status_code == 502 and response.json()['code'] == 'classification_failed'
    assert failed_once['value']
    assert client.get('/api/distractions/notes/classification/current').json()['run_id'] == run
    monkeypatch.setattr(Session, 'flush', original_flush)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(DistractionMembership).where(DistractionMembership.run_id == UUID(run))) == 4
        assert db.scalar(select(func.count()).select_from(ClassificationRun).where(ClassificationRun.user_id == uid, ClassificationRun.status == 'published')) == 1
    client.cookies.set('camp_session', str(other))
    assert client.get(detail_url, params={'kind':'topic','topic_id':group['id']}).status_code == 409


def test_browser_real_database_with_controlled_model(notes, monkeypatch):
    import json
    import socket
    import threading
    import time
    import uvicorn
    from playwright.sync_api import sync_playwright, expect
    client, sessions, uid, _, app = notes
    monkeypatch.setattr(cs, 'configuration', lambda db, user: (UUID(int=1), 1))
    def grouped(self, user, purpose, messages, request_id, **kwargs):
        units = json.loads(messages[-1]['content'])
        return {'content': cs.Result(groups=[
            {'category':'未来', 'summary':'担心求职能力', 'note_ids':[x['id'] for x in units if '求职' in x['text']]},
            {'category':'未来', 'summary':'担心学习进度', 'note_ids':[x['id'] for x in units if '学习' in x['text']]},
        ], unclassified_note_ids=[])}
    monkeypatch.setattr(cs.AIService, 'generate', grouped)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error', access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started: break
            time.sleep(.05)
        assert server.started
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 900})
            context.add_cookies([{'name':'camp_session','value':str(uid),'url':f'http://127.0.0.1:{port}'}])
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda exc: errors.append(str(exc)))
            page.goto(f'http://127.0.0.1:{port}/distractions')
            for index, content in enumerate(['求职担忧：技术能力不足', '求职担忧：岗位要求很高', '学习担忧：进度赶不上'], 1):
                page.locator('#thought-input').fill(content)
                page.locator('#thought-send').click()
                expect(page.locator('.thought-item')).to_have_count(index, timeout=15000)
            page.locator('#thought-classify').click()
            expect(page.locator('#thought-list')).to_contain_text('【2次】【未来】担心求职能力', timeout=15000)
            page.get_by_role('button', name='【2次】【未来】担心求职能力').click()
            expect(page.locator('.thought-history-entry')).to_have_count(2)
            page.reload()
            expect(page.locator('#thought-list')).to_contain_text('【2次】【未来】担心求职能力')
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors, errors
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_live_kimi_synthetic_notes(notes,monkeypatch):
    if os.environ.get('DISTRACTIONS_LIVE')!='1': pytest.skip('需要显式真实模型验证开关')
    from app.core.config import Settings
    from app.core.database import Database
    from app.modules.ai_gateway.models import AIConfig
    from app.modules.ai_gateway.service import AIService
    client,sessions,uid,_,app=notes
    settings=Settings()
    source=Database(settings)
    try:
        with source.transaction() as db:
            config=db.scalar(select(AIConfig).where(AIConfig.enabled.is_(True),AIConfig.is_default.is_(True),AIConfig.deleted_at.is_(None)))
            assert config,'未发现默认模型'
            fields={key:getattr(config,key) for key in ['base_url','model_id','encrypted_key','key_version']}
        with sessions.begin() as db:
            db.add(AIConfig(user_id=uid,name='合成杂念验证',**fields,create_request_id=uuid4(),create_fingerprint='x'*64,is_default=True,enabled=True))
            for content in ['合成：担心AI技术还不足以胜任岗位','合成：招聘要求很高，觉得自己技术还没准备好','合成：担心学习进度追不上计划']:
                service.create(db,uid,Create(request_id=uuid4(),content=content))
        # Undo fixture no-AI guard only for this explicitly enabled synthetic test.
        monkeypatch.undo()
        result=cs.classify(app.state.database,settings,uid,uuid4())
        assert result['total']==3 and sum(g['count'] for g in result['groups'])+len(result['unclassified_note_ids'])==3
        assert sorted(g['count'] for g in result['groups'])==[1,2], '语义合并未达到合成样例预期'
        assert cs.classify(app.state.database,settings,uid,uuid4())['cached']
        print('Live synthetic classification: counts=',[g['count'] for g in result['groups']], 'unclassified=',len(result['unclassified_note_ids']))
    finally: source.dispose()
