import socket
from unittest.mock import Mock
import pytest
from cryptography.fernet import Fernet
from app.core.config import Settings
from app.modules.ai_gateway import security as s


@pytest.mark.parametrize('url',[
    'http://example.com','https://u:p@example.com','https://example.com?a=1',
    'https://example.com#x','https://example.com:8443','https://127.0.0.1',
    'https://[::1]','https://169.254.169.254','https://10.0.0.1',
    'https://metadata.internal','https://example.com/%2e%2e','https://example.com/../v1',
    'https://example.com\n','file:///etc/passwd',
])
def test_unsafe_urls(url):
    with pytest.raises(s.AIError): s.base_url(url)


def test_encryption_rotation_and_missing_key():
    first,second=Fernet.generate_key().decode(),Fernet.generate_key().decode()
    old=Settings(_env_file=None,ai_encryption_keys=first)
    token=s.encrypt(old,'private-test-credential')
    assert 'private-test-credential' not in token
    combined=Settings(_env_file=None,ai_encryption_keys=second+','+first)
    assert s.decrypt(combined,token)=='private-test-credential'
    rotated=s.cipher(combined).rotate(token.encode()).decode()
    assert s.decrypt(Settings(_env_file=None,ai_encryption_keys=second),rotated)=='private-test-credential'
    with pytest.raises(s.AIError): s.decrypt(Settings(_env_file=None,ai_encryption_keys=second),token)
    with pytest.raises(s.AIError): s.encrypt(Settings(_env_file=None),'anything')


def test_all_dns_answers_checked(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(0,0,0,'',('8.8.8.8',443)),(0,0,0,'',('127.0.0.1',443))])
    with pytest.raises(s.AIError): s.resolve('example.com')
    assert not s.public_ip('::ffff:127.0.0.1')
    assert not s.public_ip('64:ff9b::a9fe:a9fe')
    assert not s.public_ip('192.0.0.8')
    assert not s.public_ip('2001:20::1')


def test_connect_pins_ip_and_retains_tls_hostname(monkeypatch):
    raw=Mock(); wrapped=Mock()
    monkeypatch.setattr(socket,'socket',lambda *a:raw)
    connection=s.PinnedHTTPS('example.com','8.8.8.8',10)
    context=Mock(); context.wrap_socket.return_value=wrapped
    connection._context=context
    connection.connect()
    raw.connect.assert_called_once_with(('8.8.8.8',443))
    context.wrap_socket.assert_called_once_with(raw,server_hostname='example.com')
    assert connection.sock is wrapped


def test_redirect_and_size_rejected_without_retry(monkeypatch):
    monkeypatch.setattr(s,'resolve',lambda host:['8.8.8.8'])
    fake=Mock(); fake.getresponse.return_value.status=302
    factory=Mock(return_value=fake)
    monkeypatch.setattr(s,'PinnedHTTPS',factory)
    with pytest.raises(s.AIError): s.post_json('https://example.com/v1','test-key',{})
    assert factory.call_count==1
    fake.getresponse.return_value.status=200
    fake.getresponse.return_value.read1.return_value=b'x'*1048577
    with pytest.raises(s.AIError,match='大小限制'): s.post_json('https://example.com/v1','test-key',{})


def test_adapter_validates_structure_and_retains_only_usage():
    from app.modules.ai_gateway.adapter import OpenAICompatibleAdapter
    from pydantic import BaseModel
    class Output(BaseModel):
        answer: str
    captured=[]
    def transport(url,key,payload):
        captured.append(payload)
        return {'choices':[{'message':{'content':'{"answer":"OK"}'}}],
                'usage':{'total_tokens':3,'prompt_tokens':-1,'completion_tokens':True,'secret':'private'}}
    content,usage=OpenAICompatibleAdapter(transport).generate('https://example.com/v1','key','model',
        [{'role':'user','content':'hello'},{'role':'assistant','content':'hi'},{'role':'user','content':'JSON please'}],Output)
    assert content.answer=='OK' and usage=={'total_tokens':3}
    assert len(captured[0]['messages'])==4
    with pytest.raises(s.AIError,match='不符合'):
        OpenAICompatibleAdapter(lambda *a:{'choices':[{'message':{'content':'{"wrong":1}'}}]}).generate('url','key','model',[],Output)


def test_generation_wait_uses_remaining_total_budget(monkeypatch):
    monkeypatch.setattr(s,'resolve',lambda host:['8.8.8.8'])
    monkeypatch.setattr(s.time,'monotonic',lambda:100.0)
    connection=Mock();connection.getresponse.return_value.status=200
    connection.getresponse.return_value.read1.side_effect=[b'{}',b'']
    factory=Mock(return_value=connection);monkeypatch.setattr(s,'PinnedHTTPS',factory)
    assert s.post_json('https://example.com/v1','test-key',{})=={}
    factory.assert_called_once_with('example.com','8.8.8.8',timeout=10)
    assert connection.sock.settimeout.call_args_list
    assert all(call.args[0]==60 for call in connection.sock.settimeout.call_args_list)
