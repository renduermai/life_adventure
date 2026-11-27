from io import BytesIO
import urllib.error
import pytest
from app.core.config import Settings
from app.modules.shining_memories.shared.storage import SupabaseStorage,validate_bucket
from app.modules.shining_memories.shared.images import MediaError

@pytest.mark.parametrize('value',[None,'','   '])
def test_missing_bucket_is_not_invalid_name(value):
    with pytest.raises(MediaError) as exc:validate_bucket(value)
    assert exc.value.code=='storage_not_configured'

@pytest.mark.parametrize('value',['XX','中文名称','x','has space'])
def test_invalid_bucket_is_distinct(value):
    with pytest.raises(MediaError) as exc:validate_bucket(value)
    assert exc.value.code=='storage_bucket_invalid'

def test_new_secret_header_and_missing_bucket_400(monkeypatch):
    store=SupabaseStorage(Settings(_env_file=None,supabase_url='https://example.supabase.co',supabase_storage_bucket='memory-private',supabase_service_role_key='sb_secret_synthetic-only'))
    class Response(BytesIO):
        def __enter__(self):return self
        def __exit__(self,*args):self.close()
    class Opener:
        def open(self,req,**kwargs):
            headers={k.lower():v for k,v in req.header_items()}
            assert headers['apikey']=='sb_secret_synthetic-only'
            assert 'authorization' not in headers
            return Response(b'{"public": false}')
    store._opener=Opener();store.ensure_private()
    class Missing:
        def open(self,req,**kwargs):
            raise urllib.error.HTTPError(req.full_url,400,'Synthetic',{},BytesIO(b'{"statusCode":"404","message":"Bucket not found"}'))
    store._opener=Missing()
    with pytest.raises(MediaError) as exc:store.ensure_private()
    assert exc.value.code=='object_missing'
