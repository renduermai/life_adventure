from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import select
from app.main import create_app
from app.core.config import Settings
from app.modules.ai_gateway import service as s
from app.modules.ai_gateway.models import AIConfig,AICallLog
from app.modules.ai_gateway.schemas import CreateConfig,EditConfig
from app.modules.ai_gateway.security import AIError,decrypt
from test_tasks_postgres import task_engine,camp

pytestmark=pytest.mark.integration


@pytest.fixture
def ai(camp):
    settings=Settings(_env_file=None,ai_encryption_keys=Fernet.generate_key().decode())
    app=create_app(settings)
    @contextmanager
    def transaction():
        with camp['sessions'].begin() as db: yield db
    app.state.database.transaction=transaction
    app.state.database.sessions=camp['sessions']
    with TestClient(app) as client:
        client.cookies.set('camp_session',str(camp['user']))
        yield camp,settings,app,client


def data(**kw):
    return dict(name='Test',base_url='https://example.com/v1',model_id='model',api_key='private-test-api-key',request_id=str(uuid4()),**kw)


def test_configuration_http_persistence_defaults_and_permissions(ai):
    camp,settings,app,client=ai
    headers={'Origin':'http://testserver'}
    payload=data()
    created=client.post('/api/ai/configs',json=payload,headers=headers)
    assert created.status_code==201,created.text
    item=created.json(); identifier=item['id']
    assert 'private-test-api-key' not in created.text and 'encrypted_key' not in created.text
    assert client.post('/api/ai/configs',json=payload,headers=headers).json()['id']==identifier
    assert client.post('/api/ai/configs',json=payload).status_code==403
    with camp['sessions']() as db:
        record=db.get(AIConfig,__import__('uuid').UUID(identifier))
        assert record.encrypted_key!='private-test-api-key'
        assert decrypt(settings,record.encrypted_key)=='private-test-api-key'
    second=client.post('/api/ai/configs',json=data(),headers=headers).json()
    firstdefault=client.post(f'/api/ai/configs/{identifier}/default',json={'expected_version':1},headers=headers)
    assert firstdefault.status_code==200
    assert client.post(f"/api/ai/configs/{second['id']}/default",json={'expected_version':1},headers=headers).status_code==200
    assert sum(c['is_default'] for c in client.get('/api/ai/configs').json())==1
    assert client.patch(f'/api/ai/configs/{identifier}',json={k:v for k,v in payload.items() if k!='request_id'}|{'expected_version':1},headers=headers).status_code==409
    assert client.put('/api/ai/module-bindings/breakdown',json={'config_id':second['id']},headers=headers).status_code==200
    assert client.put('/api/ai/module-bindings/invalid',json={'config_id':second['id']},headers=headers).status_code==422
    with camp['sessions'].begin() as db:
        with pytest.raises(AIError): s.get_config(db,camp['other'],__import__('uuid').UUID(identifier))
    invalid=client.post('/api/ai/configs',json=payload|{'name':'','api_key':'do-not-echo-this'},headers=headers)
    assert invalid.status_code==422 and 'do-not-echo-this' not in invalid.text
    assert client.request("DELETE",f"/api/ai/configs/{second['id']}",json={'expected_version':2},headers=headers).status_code==200
    assert client.get('/api/ai/module-bindings').json()=={}
    with camp['sessions']() as db:
        assert db.get(AIConfig,__import__('uuid').UUID(second['id'])).encrypted_key is None


def make(ai):
    camp,settings,app,client=ai
    with camp['sessions'].begin() as db:
        record=s.create_config(db,camp['user'],CreateConfig(**data()),settings)
        s.set_default(db,camp['user'],record.id,1)
        return record.id


def test_calls_structured_output_usage_errors_and_no_transaction(ai,monkeypatch):
    camp,settings,app,client=ai
    config_id=make(ai)
    def provider(url,key,payload):
        assert camp['engine'].pool.checkedout()==0
        assert key=='private-test-api-key'
        return {'choices':[{'message':{'content':'{"answer": "ok"}'}}], 'usage':{'total_tokens':9,'secret':'not retained'}}
    monkeypatch.setattr(s,'post_json',provider)
    class Output(BaseModel): answer:str
    gateway=s.AIService(app.state.database,settings)
    request_id=uuid4()
    result=gateway.generate(camp['user'],'breakdown',[{'role':'user','content':'Test'}],request_id,Output)
    assert result['content'].answer=='ok' and result['usage']=={'total_tokens':9}
    with pytest.raises(AIError,match='已处理'): gateway.generate(camp['user'],'breakdown',[{'role':'user','content':'Test'}],request_id,Output)
    monkeypatch.setattr(s,'post_json',lambda *a:{'choices':[{'message':{'content':'not json'}}]})
    with pytest.raises(AIError,match='不符合'): gateway.generate(camp['user'],'breakdown',[{'role':'user','content':'Test'}],uuid4(),Output)
    assert all('fingerprint' not in row for row in client.get('/api/ai/calls').json())
    def timeout(*a): raise AIError('upstream_timeout','safe timeout',504)
    monkeypatch.setattr(s,'post_json',timeout)
    response=client.post(f'/api/ai/configs/{config_id}/test',json={'expected_version':2,'request_id':str(uuid4())},headers={'Origin':'http://testserver'})
    assert response.status_code==504
    assert client.get('/api/ai/calls').json()[0]['status']=='unknown'


def test_concurrent_test_only_one_call(ai,monkeypatch):
    camp,settings,app,client=ai; config_id=make(ai)
    entered,release=Event(),Event()
    def provider(*a):
        entered.set(); assert release.wait(15)
        return {'choices':[{'message':{'content':'OK'}}]}
    monkeypatch.setattr(s,'post_json',provider)
    gateway=s.AIService(app.state.database,settings)
    request=uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        future=pool.submit(gateway.generate,camp['user'],'connection_test',[{'role':'user','content':'OK'}],request,config_id=config_id)
        try:
            assert entered.wait(15)
            with pytest.raises(AIError): gateway.generate(camp['user'],'connection_test',[{'role':'user','content':'OK'}],request,config_id=config_id)
        finally: release.set()
        assert future.result()['usage'] is None


def test_disabled_model_and_rotation(ai):
    camp,settings,app,client=ai; config_id=make(ai)
    second=Fernet.generate_key().decode()
    combined=Settings(_env_file=None,ai_encryption_keys=second+','+settings.ai_encryption_keys.get_secret_value())
    with camp['sessions'].begin() as db: assert s.rotate_keys(db,camp['user'],combined)==1
    with camp['sessions'].begin() as db:
        record=s.get_config(db,camp['user'],config_id)
        assert decrypt(Settings(_env_file=None,ai_encryption_keys=second),record.encrypted_key)=='private-test-api-key'
        s.edit_config(db,camp['user'],config_id,EditConfig(name='Test',base_url=record.base_url,model_id=record.model_id,enabled=False,expected_version=2),combined)
    with pytest.raises(AIError,match='停用'):
        s.AIService(app.state.database,combined).generate(camp['user'],'breakdown',[{'role':'user','content':'Test'}],uuid4(),config_id=config_id)
