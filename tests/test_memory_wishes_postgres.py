import os
from uuid import uuid4,UUID
import pytest
from sqlalchemy import select
from test_distractions_postgres import notes,task_engine
from test_memory_media import FakeStorage,picture
from app.modules.shining_memories.shared import service as media
from app.modules.shining_memories.shared.images import normalize_image
from app.modules.shining_memories.shared.models import MemoryAsset
from app.modules.shining_memories.wishes.models import MemoryWish,WishPrice
from app.modules.shining_memories.wishes.schemas import Category
from app.modules.ai_gateway.service import AIService
from app.modules.ai_gateway.models import AIConfig
from app.modules.ai_gateway.security import AIError
from app.core.config import Settings

pytestmark=pytest.mark.integration
BASE='/api/shining-memories/wishes';H={'Origin':'http://testserver'}
REAL_GENERATE=AIService.generate

def create(client,**extra):
    r=client.post(BASE,headers=H,json={'request_id':str(uuid4()),'name':'合成旅行心愿','price':'5000','reason':'希望放松休息',**extra})
    assert r.status_code==200,r.text
    return r.json()

def test_price_history_correction_owner_and_restart(notes):
    client,sessions,uid,other,app=notes;wish=create(client);url=BASE+'/'+wish['id']
    data={'request_id':str(uuid4()),'expected_version':1,'price':'4200'}
    r=client.post(url+'/prices',headers=H,json=data);assert r.status_code==200,r.text
    assert r.json()['initial_price']=='5000.00' and r.json()['price_change']['percentage']=='16.00'
    assert client.post(url+'/prices',headers=H,json=data).status_code==200
    assert len(client.get(url+'/prices').json()['items'])==2
    correction={'request_id':str(uuid4()),'expected_version':2,'price':'6000','note':'纠正首次录入错误'}
    fixed=client.post(url+'/initial-price-correction',headers=H,json=correction)
    assert fixed.status_code==200,fixed.text
    assert fixed.json()['initial_price']=='6000.00' and fixed.json()['current_price']=='4200.00'
    events=client.get(url+'/prices').json()['items'];assert len(events)==3 and {e['kind'] for e in events}=={'initial','update','correction'}
    with sessions() as db:assert db.get(MemoryWish,UUID(wish['id'])).current_price==4200
    client.cookies.set('camp_session',str(other));assert client.get(url).status_code==404
    assert client.post(url+'/prices',headers=H,json=data|{'request_id':str(uuid4())}).status_code==404
    client.cookies.set('camp_session',str(uid));assert client.request('DELETE',url,headers=H,json={'expected_version':3}).status_code==200
    with sessions() as db:assert len(list(db.scalars(select(WishPrice).where(WishPrice.wish_id==UUID(wish['id'])))))==3
    assert client.get(url).status_code==404

def test_cross_module_image_protection(notes):
    client,sessions,uid,other,app=notes;store=FakeStorage()
    image=media.upload(app.state.database,store,uid,normalize_image(picture(),'x.png'),uuid4())
    wish=create(client,image_asset_id=str(image['id']));url=BASE+'/'+wish['id']
    assert client.post('/api/shining-memories/items',headers=H,json={'request_id':str(uuid4()),'name':'物品','purchase_date':'2026-01-01','purchase_price':'1','image_asset_id':str(image['id'])}).status_code==409
    assert client.request('DELETE','/api/shining-memories/assets/'+str(image['id']),headers=H,params={'expected_version':1}).status_code==409
    client.cookies.set('camp_session',str(other))
    assert client.post(BASE,headers=H,json={'request_id':str(uuid4()),'name':'跨用户图片','price':'1','image_asset_id':str(image['id'])}).status_code==404
    client.cookies.set('camp_session',str(uid))
    assert client.request('DELETE',url,headers=H,json={'expected_version':1}).status_code==200
    with sessions() as db:assert db.get(MemoryAsset,image['id']).deleted_at

def test_classification_consent_cache_and_failure(notes,monkeypatch):
    client,sessions,uid,other,app=notes;wish=create(client,category='手动原类别');url=BASE+'/'+wish['id']
    with sessions.begin() as db:db.add(AIConfig(user_id=uid,create_request_id=uuid4(),create_fingerprint='f'*64,name='合成模型',base_url='https://example.com/v1',model_id='synthetic',encrypted_key='unused',key_version='none',is_default=True,enabled=True))
    calls=[]
    def generate(self,uid,purpose,messages,*args,**kwargs):
        calls.append(messages);assert purpose=='wish_category';assert set(__import__('json').loads(messages[-1]['content']))=={'name','description','reason'}
        return {'content':Category(category='旅行体验',reason='希望旅行放松')}
    monkeypatch.setattr(AIService,'generate',generate)
    data={'request_id':str(uuid4()),'expected_version':1,'consent_external':False}
    assert client.post(url+'/classify',headers=H,json=data).status_code==403 and not calls
    first=client.post(url+'/classify',headers=H,json=data|{'consent_external':True});assert first.status_code==200,first.text
    assert first.json()['category']=='旅行体验'
    second=client.post(url+'/classify',headers=H,json={'request_id':str(uuid4()),'expected_version':2,'consent_external':True})
    assert second.json()['cached'] and len(calls)==1
    edited=client.patch(url,headers=H,json={'name':'合成旅行心愿','reason':'改变原因','category':'手动新类别','image_asset_id':None,'expected_version':3})
    assert edited.status_code==200,edited.text
    def fail(*a,**kw):raise AIError('upstream_timeout','合成超时',504)
    monkeypatch.setattr(AIService,'generate',fail)
    assert client.post(url+'/classify',headers=H,json={'request_id':str(uuid4()),'expected_version':4,'consent_external':True}).status_code==504
    assert client.get(url).json()['category']=='手动新类别'

@pytest.mark.skipif(os.environ.get('RUN_WISH_AI_LIVE')!='1',reason='需显式启用真实模型合成验证')
def test_real_wish_category(notes,monkeypatch):
    from app.core.config import load_settings
    from app.core.database import Database
    from app.modules.ai_gateway.schemas import CreateConfig
    from app.modules.ai_gateway.service import create_config
    from app.modules.ai_gateway.security import decrypt
    client,sessions,uid,other,app=notes;settings=load_settings();app.state.settings=settings
    source=Database(settings)
    try:
        with source.transaction() as db:
            configs=list(db.scalars(select(AIConfig).where(AIConfig.is_default.is_(True),AIConfig.enabled.is_(True),AIConfig.deleted_at.is_(None))))
            assert len(configs)==1
            config=configs[0];values={'base_url':config.base_url,'model_id':config.model_id,'api_key':decrypt(settings,config.encrypted_key)}
    finally:source.dispose()
    with sessions.begin() as db:
        cfg=create_config(db,uid,CreateConfig(request_id=uuid4(),name='合成心愿验收',**values),settings);cfg.is_default=True
    monkeypatch.setattr(AIService,'generate',REAL_GENERATE)
    wish=create(client);r=client.post(BASE+'/'+wish['id']+'/classify',headers=H,json={'request_id':str(uuid4()),'expected_version':1,'consent_external':True})
    assert r.status_code==200,r.text
    assert r.json()['category'] and r.json()['current_price']=='5000.00'
