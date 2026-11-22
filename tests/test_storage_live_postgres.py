"""Real Storage, but disposable database users and only newly reserved object paths."""
import os,urllib.request,urllib.error
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select
from app.core.config import load_settings
from app.modules.shining_memories.shared.storage import SupabaseStorage,NoRedirect
from app.modules.shining_memories.shared.images import MediaError
from app.modules.shining_memories.shared.models import MemoryObject
from test_distractions_postgres import notes,task_engine
from test_memory_media import picture

pytestmark=pytest.mark.integration
H={'Origin':'http://testserver'}

@pytest.mark.skipif(os.environ.get('RUN_STORAGE_LIVE')!='1',reason='真实云图片测试需显式启用')
def test_real_storage_items_wishes_permissions_and_cleanup(notes,monkeypatch,capfd):
    from app.modules.shining_memories import router
    client,sessions,uid,other,app=notes;settings=load_settings();store=SupabaseStorage(settings)
    store.ensure_private()
    monkeypatch.setattr(router,'storage',lambda request,bucket=None:SupabaseStorage(settings,bucket))
    secret=settings.supabase_service_role_key.get_secret_value().encode()
    objects=set()
    try:
        for kind in ('items','wishes'):
            base='/api/shining-memories/assets'
            r=client.post(base,headers=H,params={'filename':'synthetic.png','request_id':str(uuid4())},content=picture())
            assert r.status_code==200
            asset=r.json();aid=asset['id'];url=base+'/'+aid
            with sessions() as db:
                rows=list(db.scalars(select(MemoryObject).where(MemoryObject.user_id==uid,MemoryObject.asset_id==UUID(aid))))
                old_path=rows[0].object_path;objects.update(row.object_path for row in rows)
            assert client.get(url).status_code==200
            client.cookies.set('camp_session',str(other))
            assert client.get(url).status_code==404
            assert client.put(url,headers=H,params={'filename':'foreign.png','request_id':str(uuid4()),'expected_version':1},content=picture()).status_code==404
            assert client.request('DELETE',url,headers=H,params={'expected_version':1}).status_code==404
            client.cookies.clear();assert client.get(url).status_code==401
            client.cookies.set('camp_session',str(uid))
            # Public object endpoint must not serve this real private object.
            public_url=settings.supabase_url.rstrip('/')+'/storage/v1/object/public/'+store.bucket+'/'+old_path
            try:
                with urllib.request.build_opener(NoRedirect()).open(public_url,timeout=15) as response:status=response.status
            except urllib.error.HTTPError as error:status=error.code;error.close()
            assert status!=200
            data={'request_id':str(uuid4()),'name':'云图片合成验收','image_asset_id':aid}
            data.update({'purchase_date':'2026-01-01','purchase_price':'1'} if kind=='items' else {'price':'1'})
            business='/api/shining-memories/'+kind
            saved=client.post(business,headers=H,json=data);assert saved.status_code==200
            replacement=client.put(url,headers=H,params={'filename':'replacement.png','request_id':str(uuid4()),'expected_version':1},content=picture(color='blue'))
            assert replacement.status_code==200
            assert replacement.json()['sha256']!=asset['sha256']
            assert client.get(url).status_code==200
            assert client.request('DELETE',url,headers=H,params={'expected_version':2}).status_code==409
            assert client.request('DELETE',business+'/'+saved.json()['id'],headers=H,json={'expected_version':1}).status_code==200
            assert client.get(url).status_code==404
            assert secret not in saved.content and secret not in replacement.content
    finally:
        # Includes reservations from uncertain/failed uploads. Never list or delete other paths.
        with sessions() as db:
            objects.update(db.scalars(select(MemoryObject.object_path).where(MemoryObject.user_id==uid)))
        for path in objects:
            assert path.startswith(str(uid)+'/')
            store.delete(path)
            with pytest.raises(MediaError) as exc:store.get(path)
            assert exc.value.code=='object_missing'
    captured=capfd.readouterr()
    assert secret.decode() not in captured.out+captured.err
