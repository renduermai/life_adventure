import base64
import json
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.main import create_app
from app.modules.ai_gateway import router


def jwt(role):
    def segment(value):return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')
    return segment({'alg':'HS256'})+'.'+segment({'role':role})+'.synthetic_signature'


def test_display_missing_fields_and_safe_dashboard():
    settings=Settings(_env_file=None)
    data,key=router.supabase_display(settings)
    assert key is None and not data['configured'] and data['project_url'] is None
    assert not data['server_key_configured'] and not data['public_key_configured']
    assert data['dashboard_url']=='https://supabase.com/dashboard'
    settings.supabase_url='https://'+'a'*20+'.supabase.co'
    data,_=router.supabase_display(settings)
    assert data['dashboard_url']=='https://supabase.com/dashboard/project/'+'a'*20
    for url in ['https://custom.example','https://short-ref.supabase.co']:
        settings.supabase_url=url
        assert router.supabase_display(settings)[0]['dashboard_url']=='https://supabase.com/dashboard'
    for url in ['javascript:alert(1)','https://secret@example.com','https://example.com?key=private','https://example.com/private','https://[bad']:
        settings.supabase_url=url
        data,_=router.supabase_display(settings)
        assert data['project_url'] is None and 'private' not in json.dumps(data)


@pytest.mark.parametrize('name,value',[
    ('supabase_publishable_key','sb_secret_SYNTHETIC_PRIVATE'),
    ('supabase_publishable_key',jwt('service_role')),
    ('supabase_anon_key',jwt('service_role')),
    ('supabase_anon_key','not-a-public-key'),
])
def test_server_or_invalid_keys_never_disclosed(name,value):
    settings=Settings(_env_file=None,**{name:value},supabase_service_role_key='sb_secret_OTHER_PRIVATE')
    metadata,key=router.supabase_display(settings)
    assert key is None and not metadata['public_key_configured'] and metadata['public_key_invalid']
    assert value not in json.dumps(metadata) and 'OTHER_PRIVATE' not in json.dumps(metadata)


def test_public_key_priority_fallback_and_no_server_duplicate():
    public='sb_publishable_SYNTHETIC_PUBLIC'
    settings=Settings(_env_file=None,supabase_publishable_key=public,supabase_anon_key=jwt('anon'),supabase_secret_key='sb_secret_PRIVATE')
    metadata,key=router.supabase_display(settings)
    assert key==public and metadata['public_key_type']=='Publishable Key' and metadata['server_key_configured']
    settings.supabase_publishable_key=None
    assert router.supabase_display(settings)[1]==jwt('anon')
    settings.supabase_service_role_key=settings.supabase_anon_key
    assert router.supabase_display(settings)[1] is None


def test_metadata_and_copy_response_boundaries(monkeypatch,caplog):
    private='sb_secret_SYNTHETIC_NEVER_EXPOSE'
    public='sb_publishable_SYNTHETIC_COPY_ONLY'
    app=create_app(Settings(_env_file=None,supabase_publishable_key=public,supabase_service_role_key=private))
    monkeypatch.setattr(router,'user_id',lambda request:uuid4())
    caplog.set_level('INFO',logger='adventure_camp')
    with TestClient(app) as client:
        listing=client.get('/api/ai/supabase')
        assert listing.status_code==200 and private not in listing.text and public not in listing.text
        assert listing.headers['cache-control']=='no-store'
        page=client.get('/spirit-stones')
        script=client.get('/static/js/spirit_stones.js')
        assert private not in page.text+script.text and public not in page.text+script.text
        assert client.post('/api/ai/supabase/public-key/copy').status_code==403
        assert client.post('/api/ai/supabase/public-key/copy',headers={'Origin':'https://other.example'}).status_code==403
        copied=client.post('/api/ai/supabase/public-key/copy',headers={'Origin':'http://testserver'})
        assert copied.json()=={'public_key':public} and copied.headers['cache-control']=='no-store'
        assert private not in copied.text
        app.state.settings.supabase_publishable_key=None
        missing=client.post('/api/ai/supabase/public-key/copy',headers={'Origin':'http://testserver'})
        assert missing.status_code==409 and private not in missing.text
    assert private not in caplog.text and public not in caplog.text
