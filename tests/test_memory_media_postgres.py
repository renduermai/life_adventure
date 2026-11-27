from datetime import timedelta
from uuid import UUID, uuid4
import base64
import os
import pytest
from sqlalchemy import select
from app.core.config import Settings
from app.modules.shining_memories.shared import service
from app.modules.shining_memories.shared.models import MemoryAsset, MemoryObject
from app.modules.shining_memories.shared.backup import backup_media, restore_media
from app.modules.shining_memories.shared.images import normalize_image
from test_distractions_postgres import notes, task_engine
from test_memory_media import FakeStorage, picture

pytestmark=pytest.mark.integration
BASE='/api/shining-memories/assets'
HEADERS={'Origin':'http://testserver'}


@pytest.fixture
def media(notes, monkeypatch):
    from app.modules.shining_memories import router
    store=FakeStorage()
    monkeypatch.setattr(router,'storage',lambda request,bucket=None:store)
    return notes,store


def send(client, path=BASE, method='POST', version=None, color='red', request_id=None):
    params={'filename':'test.png','request_id':str(request_id or uuid4())}
    if version: params['expected_version']=version
    return client.request(method,path,headers=HEADERS,params=params,content=picture(color=color))


def test_cloud_lifecycle_permissions_and_restart(media):
    (client,sessions,uid,other,app),store=media
    request_id=uuid4()
    first=send(client,request_id=request_id)
    assert first.status_code==200,first.text
    asset=first.json(); path=BASE+'/'+asset['id']
    assert send(client,request_id=request_id).json()==asset and len(store.objects)==1
    assert client.get(path).status_code==200
    assert 'no-store' in client.get(path).headers['cache-control']
    client.cookies.set('camp_session',str(other))
    assert client.get(path).status_code==404
    assert client.request('DELETE',path,headers=HEADERS,params={'expected_version':1}).status_code==404
    client.cookies.set('camp_session',str(uid))
    store.failure=True
    assert send(client,path,'PUT',1,'blue').status_code==503
    store.failure=False
    assert client.get(path+'/metadata').json()['version']==1
    assert send(client,path,'PUT',1,'blue').json()['version']==2
    assert send(client,path,'PUT',1,'green').status_code==409
    with sessions() as db:
        objects=list(db.scalars(select(MemoryObject).where(MemoryObject.asset_id==UUID(asset['id']))))
        assert sum(obj.state=='active' for obj in objects)==1
        assert all(str(uid)+'/' in obj.object_path and ':' not in obj.object_path for obj in objects)
    # Fresh application reads committed data with the same login and no in-memory state.
    from app.main import create_app
    from fastapi.testclient import TestClient
    fresh=create_app(Settings(_env_file=None))
    fresh.state.database.sessions=sessions
    fresh.state.database.transaction=app.state.database.transaction
    with TestClient(fresh) as browser:
        browser.cookies.set('camp_session',str(uid))
        assert browser.get(path).status_code==200
    assert client.request('DELETE',path,headers=HEADERS,params={'expected_version':2}).status_code==200
    assert client.get(path).status_code==404
    assert len(store.objects)==2  # Delayed removal, not public access.
    with sessions.begin() as db:
        for obj in db.scalars(select(MemoryObject).where(MemoryObject.asset_id==UUID(asset['id']))):
            obj.delete_after=service.now()-timedelta(seconds=1)
    store.failure=True
    assert service.cleanup(app.state.database,lambda bucket:store)['failed']>=1
    store.failure=False
    assert service.cleanup(app.state.database,lambda bucket:store)['removed']>=1
    assert not store.objects


def test_real_database_snapshot_encryption_restore(media,tmp_path):
    (client,sessions,uid,other,app),store=media
    assert send(client).status_code==200
    settings=Settings(_env_file=None,memory_backup_dir=tmp_path,
        memory_backup_key=base64.urlsafe_b64encode(os.urandom(32)).decode())
    result=backup_media(app.state.database,settings,lambda bucket:store)
    assert result['images']==1
    target=FakeStorage('memory-restore')
    restored=restore_media(result['path'],settings.memory_backup_key,target)
    assert restored['restored']==1 and restored['verified'] and not restored['database_changed']
    assert target.objects==store.objects
