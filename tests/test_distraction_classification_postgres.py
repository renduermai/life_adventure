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
