import base64
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile, ZIP_STORED
import json
import os
import pytest
from PIL import Image
from pydantic import SecretStr
from app.core.config import Settings
from app.modules.shining_memories.shared.images import normalize_image, MediaError, MAX_BYTES
from app.modules.shining_memories.shared.storage import SupabaseStorage, validate_object_path
from app.modules.shining_memories.shared.backup import EncryptedWriter, open_backup, restore_media
from app.core.database import EXPECTED_REVISION


def picture(format='PNG', color='red'):
    buf = BytesIO()
    Image.new('RGB', (12, 10), color).save(buf, format=format)
    return buf.getvalue()


class FakeStorage:
    def __init__(self, bucket='memory-private'):
        self.bucket, self.objects, self.private = bucket, {}, True
        self.failure = False

    def ensure_private(self, create=False):
        if not self.private:
            raise MediaError('public_bucket', 'Private required', 503)

    def put(self, path, data):
        if self.failure:
            raise MediaError('storage_unavailable', 'Synthetic timeout', 503)
        assert path not in self.objects
        self.objects[path] = data

    def get(self, path):
        return self.objects[path]

    def delete(self, path):
        if self.failure:
            raise MediaError('storage_unavailable', 'Synthetic failure', 503)
        self.objects.pop(path, None)

    def is_empty(self):
        return not self.objects


@pytest.mark.parametrize('fmt,extension', [('PNG','png'),('JPEG','jpg'),('WEBP','webp')])
def test_image_normalizes_to_metadata_free_webp(fmt, extension):
    result = normalize_image(picture(fmt), 'test.' + extension)
    with Image.open(BytesIO(result.data)) as image:
        assert image.format == 'WEBP' and image.size == (12,10) and not image.getexif()


@pytest.mark.parametrize('data,name', [(b'invalid','a.png'),(picture(),'a.jpg'),(picture(),'../a.png'),
    (picture(),'C:\\private\\a.png'),(picture(),'a.svg'),(b'', 'a.png'),(b'x'*(MAX_BYTES+1),'a.png')])
def test_invalid_uploads_are_rejected(data, name):
    with pytest.raises(MediaError):
        normalize_image(data, name)


def test_public_bucket_refused_and_credentials_not_exposed(monkeypatch):
    store = SupabaseStorage(Settings(_env_file=None, supabase_url='https://example.supabase.co',
        supabase_service_role_key='private-sentinel', supabase_storage_bucket='memory-private'))
    monkeypatch.setattr(store, '_json', lambda *args, **kwargs: {'public':True})
    with pytest.raises(MediaError, match='私有') as error:
        store.ensure_private()
    assert 'private-sentinel' not in str(error.value)
    for path in ('../x','a/b/c','file:///C:/x','https://example.com/x'):
        with pytest.raises(MediaError): validate_object_path(path)


def test_foundation_pages_and_unconfigured_auth(client):
    for section in ('people','items','wishes'):
        response = client.get('/shining-memories/'+section)
        assert response.status_code == 200 and '闪光的回忆' in response.text
        assert 'aria-current="page"' in response.text
    assert client.get('/shining-memories/missing').status_code == 404
    assert client.get('/api/shining-memories/status').status_code == 503
    assert client.post('/api/shining-memories/assets',content=b'x').status_code == 403


def archive_sample(tmp_path):
    from hashlib import sha256
    data = normalize_image(picture(), 'x.png').data
    owner, obj = uuid4(), uuid4()
    path = f'{owner}/{obj}.webp'
    manifest = {'format':'adventure-memory-media','version':1,'revision':EXPECTED_REVISION,
        'scope':'current_active_images','assets':[{'user_id':str(owner),'object_id':str(obj),
        'asset_id':str(uuid4()),'version':1,'bucket':'memory-private','object_path':path,
        'file':'objects/'+path,'byte_size':len(data),'sha256':sha256(data).hexdigest(),
        'width':12,'height':10,'content_type':'image/webp'}]}
    key = os.urandom(32)
    target=tmp_path/'sample.acmedia'
    with target.open('wb') as output:
        writer=EncryptedWriter(output,key)
        with ZipFile(writer,'w',compression=ZIP_STORED) as archive:
            archive.writestr('manifest.json',json.dumps(manifest))
            archive.writestr('objects/'+path,data)
        writer.finish()
    return target,SecretStr(base64.urlsafe_b64encode(key).decode()),manifest


def test_encrypted_backup_restore_and_no_overwrite(tmp_path):
    target,key,manifest=archive_sample(tmp_path)
    assert b'manifest.json' not in target.read_bytes()
    store=FakeStorage('memory-restore')
    assert restore_media(target,key,store)['verified']
    assert len(store.objects)==1
    with pytest.raises(MediaError,match='为空'):
        restore_media(target,key,store)
    with pytest.raises(MediaError,match='来源'):
        restore_media(target,key,FakeStorage())
    with pytest.raises(MediaError):
        restore_media(target,SecretStr(base64.urlsafe_b64encode(os.urandom(32)).decode()),FakeStorage('memory-restore'))
    data=bytearray(target.read_bytes()); data[len(data)//2]^=1; target.write_bytes(data)
    untouched=FakeStorage('memory-restore')
    with pytest.raises(MediaError): restore_media(target,key,untouched)
    assert not untouched.objects
