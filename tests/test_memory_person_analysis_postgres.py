import os
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func
from app.modules.ai_gateway.models import AIConfig
from app.modules.ai_gateway.service import AIService
from app.modules.ai_gateway.security import AIError
from app.modules.shining_memories.people.analysis_models import PersonAnalysis
from app.modules.distractions.models import DistractionNote
from test_distractions_postgres import notes,task_engine
from test_memory_person_analysis import output

pytestmark=pytest.mark.integration
H={'Origin':'http://testserver'}
BASE='/api/shining-memories/people'
REAL_GENERATE=AIService.generate


def setup(notes):
    client,sessions,uid,other,app=notes
    with sessions.begin() as db:
        cfg=AIConfig(user_id=uid,create_request_id=uuid4(),create_fingerprint='x'*64,name='合成测试模型',base_url='https://example.com/v1',
            model_id='synthetic',encrypted_key='unused',key_version='unused',enabled=True,is_default=True)
        db.add(cfg)
    r=client.post(BASE,headers=H,json={'request_id':str(uuid4()),'name':'合成老师','relationship':'老师','precious_moments':'老师曾给予机会。','contact_preference':'willing'})
    assert r.status_code==200,r.text
    return client,sessions,uid,other,app,r.json(),BASE+'/'+r.json()['id']


def preview(client,url,scope=None):
    response=client.post(url+'/preview',headers=H,json=scope or {})
    assert response.status_code==200,response.text
    return response.json()


def run(client,url,p,scope=None,consent=True):
    return client.post(url+'/analysis',headers=H,json=(scope or {})|{'request_id':str(uuid4()),'preview_token':p['preview_token'],'consent_external':consent})


def test_consent_scope_cache_failure_stale_and_ranking(notes,monkeypatch):
    client,sessions,uid,other,app,person,url=setup(notes);calls=[]
    def generate(*args,**kwargs):
        calls.append(args[2]);return {'content':output()}
    monkeypatch.setattr(AIService,'generate',generate)
    p=preview(client,url);assert not p['payload']['selected']
    assert run(client,url,p,consent=False).status_code==403 and not calls
    success=run(client,url,p);assert success.status_code==200,success.text
    assert success.json()['recommendation']['score']==45 and len(calls)==1
    assert run(client,url,p).json()['cached'] and len(calls)==1
    assert client.get(BASE).json()['items'][0]['recommendation']['score']==45
    updated={k:person[k] for k in ('name','relationship','precious_moments','manual_contact_date','contact_preference','notes')}
    assert client.patch(url,headers=H,json=updated|{'notes':'新增合成备注','expected_version':person['version']}).status_code==200
    assert run(client,url,p).status_code==409
    p=preview(client,url)
    def failure(*args,**kwargs):raise AIError('upstream_timeout','合成超时',504)
    monkeypatch.setattr(AIService,'generate',failure)
    assert run(client,url,p).status_code==504
    saved=client.get(url+'/analysis').json()
    assert saved['analysis']['meaning_label']=='给予机会的老师' and saved['stale']
    assert saved['last_attempt']['error_code']=='upstream_timeout'
    client.cookies.set('camp_session',str(other));assert client.get(url+'/analysis').status_code==404


def test_authorized_notes_sources_and_invalid_output_preserve(notes,monkeypatch):
    client,sessions,uid,other,app,person,url=setup(notes)
    nid=uuid4()
    with sessions.begin() as db:db.add(DistractionNote(id=nid,user_id=uid,content='合成杂念，不可默认外发',create_request_id=uuid4(),create_fingerprint='a'*64))
    assert client.post(url+'/preview',headers=H,json={'note_ids':[str(nid)]}).status_code==422
    scope={'include_notes':True,'note_ids':[str(nid)]}
    p=preview(client,url,scope);assert 'note:'+str(nid) in p['payload']['sources']
    assert 'note:'+str(nid) not in preview(client,url)['payload']['sources']
    monkeypatch.setattr(AIService,'generate',lambda *a,**kw:{'content':output()})
    assert run(client,url,p,scope).status_code==200
    with sessions.begin() as db:db.get(DistractionNote,nid).content='合成来源已变化'
    assert client.get(url+'/analysis').json()['stale']
    p=preview(client,url,scope)
    bad=output();bad.meaning.evidence[0].quote='不存在的引文'
    monkeypatch.setattr(AIService,'generate',lambda *a,**kw:{'content':bad})
    assert run(client,url,p,scope).status_code==502
    assert client.get(url+'/analysis').json()['analysis']['meaning_label']=='给予机会的老师'


@pytest.mark.skipif(os.environ.get('RUN_MEMORY_AI_LIVE')!='1',reason='真实模型合成验证需显式RUN_MEMORY_AI_LIVE=1')
def test_real_model_synthetic_person(notes,monkeypatch):
    from dotenv import dotenv_values
    from app.core.config import load_settings
    from app.modules.ai_gateway.schemas import CreateConfig
    from app.modules.ai_gateway.service import create_config
    client,sessions,uid,other,app=notes
    settings=load_settings();values=dotenv_values('.env')
    # Prefer the actual current default over potentially stale AI_TEST_* settings.
    from app.core.database import Database
    from app.modules.ai_gateway.security import decrypt
    source=Database(settings)
    try:
        with source.transaction() as db:
            defaults=list(db.scalars(select(AIConfig).where(AIConfig.is_default.is_(True),AIConfig.enabled.is_(True),AIConfig.deleted_at.is_(None))))
            if len(defaults)!=1:pytest.skip('真实验收需明确唯一的当前默认模型')
            current=defaults[0]
            values={'AI_TEST_BASE_URL':current.base_url,'AI_TEST_MODEL':current.model_id,'AI_TEST_API_KEY':decrypt(settings,current.encrypted_key)}
    finally:source.dispose()
    app.state.settings=settings
    with sessions.begin() as db:
        cfg=create_config(db,uid,CreateConfig(request_id=uuid4(),name='合成人物验收',base_url=values['AI_TEST_BASE_URL'],
            model_id=values['AI_TEST_MODEL'],api_key=values['AI_TEST_API_KEY']),settings)
        cfg.is_default=True
    monkeypatch.setattr(AIService,'generate',REAL_GENERATE)
    from app.modules.ai_gateway import security
    import re,json
    original_response=security.PinnedHTTPS.getresponse
    def diagnostic_response(connection,*args,**kwargs):
        response=original_response(connection,*args,**kwargs)
        if response.status!=200:
            code=None
            try:
                body=json.loads(response.read(16384))
                error=body.get('error',body)
                value=error.get('code') if isinstance(error,dict) else None
                if isinstance(value,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,60}',value):code=value
            except (ValueError,TypeError):pass
            print('Provider diagnostic HTTP:',response.status,'code:',code)
        return response
    monkeypatch.setattr(security.PinnedHTTPS,'getresponse',diagnostic_response)
    r=client.post(BASE,headers=H,json={'request_id':str(uuid4()),'name':'合成导师A','relationship':'老师',
        'precious_moments':'在我缺少经验时，他给予机会，让我承担一个练习项目。我愿意告诉他练习项目的进展。','contact_preference':'willing'})
    assert r.status_code==200,r.text
    url=BASE+'/'+r.json()['id'];p=preview(client,url)
    r=run(client,url,p)
    print('Synthetic live model HTTP:',r.status_code,'error_code:',r.json().get('code'))
    assert r.status_code==200,r.text
    assert r.json()['analysis'] and r.json()['recommendation']['score'] is not None
