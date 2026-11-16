"""Authenticated encryption and connection-time destination policy."""
import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
import time
from queue import Queue, Empty
from threading import BoundedSemaphore, Thread
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, MultiFernet


class AIError(ValueError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


def cipher(settings):
    try:
        keys = settings.ai_encryption_keys.get_secret_value().split(',')
        return MultiFernet([Fernet(key.strip().encode()) for key in keys])
    except Exception:
        raise AIError('encryption_unavailable', '请配置有效的 AI 加密主密钥', 503) from None


def key_version(settings):
    cipher(settings)
    return hashlib.sha256(settings.ai_encryption_keys.get_secret_value().split(',')[0].strip().encode()).hexdigest()[:16]


def encrypt(settings, value):
    return cipher(settings).encrypt(value.encode()).decode()


def decrypt(settings, value):
    try:
        return cipher(settings).decrypt(value.encode()).decode()
    except Exception:
        raise AIError('decryption_failed', '无法读取模型密钥，请检查主密钥或重新填写', 503) from None


def public_ip(value):
    address = ipaddress.ip_address(value)
    # Conservative special-purpose exclusions also on Python 3.11's older registry.
    special = ('192.0.0.0/24', '192.88.99.0/24') if address.version == 4 else ('2001::/23',)
    if any(address in ipaddress.ip_network(net) for net in special):
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped or address.sixtofour or address.teredo or address in ipaddress.ip_network('64:ff9b::/96') or address in ipaddress.ip_network('64:ff9b:1::/48'):
            return False
    return address.is_global and not address.is_multicast and not address.is_reserved


def base_url(value):
    try:
        url = urlsplit(value)
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.port not in (None, 443)
                or any(ord(c) <= 32 or ord(c) == 127 for c in value) or '\\' in value
                or '%' in value or '..' in url.path):
            raise ValueError()
        host = url.hostname.encode('idna').decode('ascii').lower()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if '.' not in host or host.endswith(('.local', '.internal', '.localhost')):
                raise ValueError()
        else:
            if not public_ip(str(address)):
                raise AIError('unsafe_url', '模型地址必须是公网 HTTPS 地址')
        return 'https://' + ('[' + host + ']' if ':' in host else host) + url.path.rstrip('/')
    except AIError:
        raise
    except Exception:
        raise AIError('unsafe_url', '模型地址须为 HTTPS 公网地址，端口 443，不含凭据、查询或片段') from None


_dns_slots = BoundedSemaphore(4)


def resolve(host):
    if not _dns_slots.acquire(blocking=False):
        raise AIError('dns_busy', '地址解析繁忙，请稍后重试', 503)
    result = Queue(maxsize=1)
    def lookup():
        try:
            result.put(socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM))
        except Exception:
            result.put(None)
        finally:
            _dns_slots.release()
    Thread(target=lookup, daemon=True).start()
    try:
        answers = result.get(timeout=10)
        addresses = list(dict.fromkeys(item[4][0] for item in (answers or [])))
        if not addresses or not all(public_ip(ip) for ip in addresses):
            raise ValueError()
        # Prefer IPv4 on hosts without an IPv6 route; never retry a sent request.
        return sorted(addresses, key=lambda ip: ipaddress.ip_address(ip).version)
    except Empty:
        raise AIError('dns_timeout', '模型地址解析超时', 504) from None
    except Exception:
        raise AIError('unsafe_destination', '模型域名无法解析为允许的公网地址', 502) from None


class PinnedHTTPS(http.client.HTTPSConnection):
    """Connect to a validated numeric IP; verify TLS against original hostname."""
    def __init__(self, host, ip, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.ip = ip

    def connect(self):
        family = socket.AF_INET6 if ':' in self.ip else socket.AF_INET
        raw = socket.socket(family, socket.SOCK_STREAM)
        try:
            raw.settimeout(self.timeout)
            raw.connect((self.ip, 443))
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def post_json(url, key, payload, *, timeout_seconds=60):
    if timeout_seconds not in (60, 90):
        raise ValueError("Unsupported request budget")
    target = urlsplit(base_url(url))
    started = time.monotonic()
    addresses = resolve(target.hostname)
    if time.monotonic() - started >= 10:
        raise AIError('dns_timeout', '模型地址解析超时', 504)
    connection = PinnedHTTPS(target.hostname, addresses[0], timeout=10)
    # A timer closes this one connection, including slow response headers/body.
    from threading import Timer
    timer = Timer(max(0.01, timeout_seconds - (time.monotonic() - started)), connection.close)
    timer.daemon = True
    try:
        timer.start()
        connection.request('POST', (target.path or '') + '/chat/completions',
                           body=json.dumps(payload).encode(), headers={
                               'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                               'Accept': 'application/json', 'Accept-Encoding': 'identity'})
        # Connecting is bounded by 10s; generation may use the remaining total
        # deadline. Non-streaming providers often send headers only after generation.
        remaining = timeout_seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError()
        if connection.sock is not None:
            connection.sock.settimeout(remaining)
        response = connection.getresponse()
        if response.status != 200:
            code = 'upstream_rejected' if response.status != 429 else 'upstream_rate_limit'
            raise AIError(code, '供应商拒绝请求，请检查模型、凭据或额度', 502)
        chunks = bytearray()
        while True:
            if time.monotonic() - started >= timeout_seconds:
                raise TimeoutError()
            if connection.sock is not None:
                connection.sock.settimeout(max(.01, timeout_seconds - (time.monotonic() - started)))
            block = response.read1(min(65536, 1048577 - len(chunks)))
            if not block:
                break
            chunks.extend(block)
            if len(chunks) > 1048576:
                raise AIError('response_too_large', '模型响应超过大小限制', 502)
        return json.loads(chunks)
    except AIError:
        raise
    except (TimeoutError, socket.timeout):
        raise AIError('upstream_timeout', '模型请求超时，可能已计费；请主动重试', 504) from None
    except Exception:
        raise AIError('upstream_failed', '模型连接失败或响应无效；未自动重试', 502) from None
    finally:
        timer.cancel()
        connection.close()
