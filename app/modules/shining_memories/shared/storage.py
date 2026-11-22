"""Small Supabase REST boundary. Credentials and response bodies never escape."""
import json
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import quote, urlsplit
from uuid import UUID

from .images import MAX_BYTES, MediaError


def validate_bucket(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        raise MediaError('storage_not_configured', '云端图片存储尚未配置，请配置存储桶名称', 503)
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,62}', value):
        raise MediaError('storage_bucket_invalid', '存储桶名称需为3–63位小写字母、数字或连字符，且以字母或数字开头', 503)
    return value


def validate_object_path(value):
    try:
        owner, name = value.split('/')
        UUID(owner)
        UUID(name.removesuffix('.webp'))
        if not name.endswith('.webp') or value != f'{str(UUID(owner))}/{str(UUID(name[:-5]))}.webp':
            raise ValueError()
    except (ValueError, AttributeError, TypeError):
        raise MediaError('object_path', '图片对象标识无效') from None
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class SupabaseStorage:
    def __init__(self, settings, bucket=None):
        self.bucket = validate_bucket(bucket or settings.supabase_storage_bucket or '')
        url = settings.supabase_url or ''
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or not parsed.hostname or
                not re.fullmatch(r'[a-z0-9-]+\.supabase\.co', parsed.hostname) or
                parsed.username or parsed.password or parsed.port not in (None, 443) or
                parsed.path not in ('', '/') or parsed.query or parsed.fragment):
            raise MediaError('storage_not_configured', '请配置有效的Supabase项目HTTPS地址', 503)
        if not settings.supabase_service_role_key:
            raise MediaError('storage_not_configured', '云端图片尚未配置服务端存储凭据', 503)
        self.url = url.rstrip('/') + '/storage/v1'
        self._key = settings.supabase_service_role_key.get_secret_value()
        # Respect Windows/system proxy settings; keep HTTPS and redirect rejection.
        self._opener = urllib.request.build_opener(NoRedirect())

    def _request(self, method, path, data=None, content_type='application/json', limit=MAX_BYTES):
        headers = {'apikey': self._key, 'Content-Type': content_type}
        # New Supabase secret keys are opaque API keys, not JWT bearer tokens.
        if not self._key.startswith('sb_secret_'):
            headers['Authorization'] = 'Bearer ' + self._key
        request = urllib.request.Request(self.url + path, data=data, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=20) as response:
                body = response.read(limit + 1)
                if len(body) > limit:
                    raise MediaError('storage_response', '云端响应超过允许大小', 502)
                return body
        except urllib.error.HTTPError as error:
            status = error.code
            provider_code = None
            try:
                payload = json.loads(error.read(16384))
                provider_code = payload.get('code') if isinstance(payload, dict) else None
                # Some Storage versions wrap missing resources in HTTP 400.
                missing = provider_code in {'NoSuchBucket', 'NoSuchKey', 'not_found'} or (
                    isinstance(payload, dict) and str(payload.get('statusCode')) == '404')
            except (ValueError, TypeError, OSError):
                missing = False
            error.close()
            if status == 404 or missing:
                raise MediaError('object_missing', '云端对象或存储桶不存在', 502) from None
            if status in (401, 403):
                raise MediaError('storage_auth', '云端存储认证失败，请检查服务端配置', 503) from None
            if status in (409, 400):
                raise MediaError('storage_conflict', '云端对象冲突或存储参数无效', 502) from None
            raise MediaError('storage_failure', '云端存储请求失败，请稍后重试', 502) from None
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
            raise MediaError('storage_unavailable', '云端存储连接失败或超时，请稍后重试', 503) from None

    def _json(self, method, path, payload=None):
        body = self._request(method, path, None if payload is None else json.dumps(payload).encode())
        try:
            return json.loads(body)
        except (ValueError, TypeError):
            raise MediaError('storage_response', '云端存储响应格式异常', 502) from None

    def ensure_private(self, create=False):
        try:
            info = self._json('GET', '/bucket/' + self.bucket)
        except MediaError as error:
            if not create or error.code != 'object_missing':
                raise
            self._json('POST', '/bucket', {'id': self.bucket, 'name': self.bucket, 'public': False,
                'file_size_limit': MAX_BYTES, 'allowed_mime_types': ['image/webp']})
            info = self._json('GET', '/bucket/' + self.bucket)
        if not isinstance(info, dict) or info.get('public') is not False:
            raise MediaError('public_bucket', '存储桶必须设为私有；已拒绝图片操作', 503)

    def put(self, path, data):
        validate_object_path(path)
        # POST without upsert: every revision has an immutable, random object key.
        self._request('POST', '/object/' + self.bucket + '/' + quote(path, safe='/'), data, 'image/webp')

    def get(self, path):
        validate_object_path(path)
        return self._request('GET', '/object/authenticated/' + self.bucket + '/' + quote(path, safe='/'))

    def delete(self, path):
        validate_object_path(path)
        self._json('DELETE', '/object/' + self.bucket, {'prefixes': [path]})

    def is_empty(self):
        rows = self._json('POST', '/object/list/' + self.bucket, {'prefix': '', 'limit': 1, 'offset': 0})
        if not isinstance(rows, list):
            raise MediaError('storage_response', '云端对象列表响应异常', 502)
        return not rows
