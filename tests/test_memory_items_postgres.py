from datetime import timedelta
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select
from test_distractions_postgres import notes,task_engine
from test_memory_media import FakeStorage,picture
from app.modules.shining_memories.people.service import today
from app.modules.shining_memories.shared import service as media
from app.modules.shining_memories.shared.images import normalize_image
from app.modules.shining_memories.shared.models import MemoryAsset
from app.modules.shining_memories.items.models import MemoryItem

pytestmark=pytest.mark.integration
BASE='/api/shining-memories/items'
H={'Origin':'http://testserver'}

def test_items_cost_categories_owner_and_images(notes):
    client,sessions,uid,other,app=notes;store=FakeStorage()
    with sessions() as db:day=today(db,uid)
    image=media.upload(app.state.database,store,uid,normalize_image(picture(),'x.png'),uuid4())
    data={'request_id':str(uuid4()),'name':'合成物品','purchase_date':str(day-timedelta(days=400)),
          'purchase_price':'8000.00','category':'电子产品','image_asset_id':str(image['id'])}
    first=client.post(BASE,headers=H,json=data);assert first.status_code==200,first.text
    item=first.json();assert item['daily_cost']=='20.00' and item['days']==400
    assert client.post(BASE,headers=H,json=data).json()['id']==item['id']
    assert client.post(BASE,headers=H,json=data|{'request_id':str(uuid4())}).status_code==409
    assert client.request('DELETE','/api/shining-memories/assets/'+str(image['id']),headers=H,params={'expected_version':1}).status_code==409
    assert client.post(BASE,headers=H,json=data|{'request_id':str(uuid4()),'image_asset_id':None,'purchase_date':str(day+timedelta(days=1))}).status_code==422
    client.cookies.set('camp_session',str(other));assert client.get(BASE+'/'+item['id']).status_code==404
    assert client.post(BASE,headers=H,json=data|{'request_id':str(uuid4())}).status_code==404
    client.cookies.set('camp_session',str(uid))
    edit={k:data[k] for k in ('name','purchase_date','purchase_price','category','image_asset_id')}|{'category':'学习','expected_version':1}
    assert client.patch(BASE+'/'+item['id'],headers=H,json=edit).json()['version']==2
    assert client.get(BASE,params={'category':'学习'}).json()['total']==1
    assert client.request('DELETE',BASE+'/'+item['id'],headers=H,json={'expected_version':2}).status_code==200
    with sessions() as db:assert db.get(MemoryAsset,image['id']).deleted_at is not None and db.get(MemoryItem,UUID(item['id'])).deleted_at is not None

def test_sort_and_neutral_thresholds(notes):
    client,sessions,uid,other,app=notes
    with sessions() as db:day=today(db,uid)
    for price in ('2','1','3'):
        r=client.post(BASE,headers=H,json={'request_id':str(uuid4()),'name':'物品'+price,'purchase_date':str(day),'purchase_price':price})
        assert r.status_code==200,r.text
    items=client.get(BASE).json()['items']
    assert [x['daily_cost'] for x in items]==['1.00','2.00','3.00']
    assert [x['cost_band'] for x in items]==['low','medium','high']
