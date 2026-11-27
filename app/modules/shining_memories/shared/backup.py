"""Encrypted, streamed media snapshots; restore into an empty private bucket only."""
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import tempfile
from uuid import UUID, uuid4
from zipfile import ZipFile, ZIP_STORED, BadZipFile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy import select, text
from app.core.database import EXPECTED_REVISION
from .images import MAX_BYTES, MediaError
from .models import MemoryAsset, MemoryObject
from .service import BACKUP_LOCK
from .storage import validate_object_path, validate_bucket

MAGIC = b'ACMEDIA1\n'
MAX_MANIFEST = 8 * 1024 * 1024
MAX_ENTRIES = 10_000
SUPPORTED_MEDIA_REVISIONS = {'0022_memory_assets', '0024_person_analysis', '0025_memory_items', '0026_memory_wishes', '0027_item_entitlements'}


def encryption_key(secret):
    try:
        value = base64.b64decode(secret.get_secret_value(), altchars=b'-_', validate=True)
        if len(value) != 32:
            raise ValueError()
        return value
    except (ValueError, TypeError, AttributeError):
        raise MediaError('backup_key', '请配置独立的32字节URL-safe Base64备份密钥', 503) from None


class EncryptedWriter:
    """Non-seekable ZIP output, encrypted before it touches the filesystem."""
    def __init__(self, stream, key):
        self.stream, self.position = stream, 0
        nonce = os.urandom(12)
        self.encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
        header = MAGIC + nonce
        self.encryptor.authenticate_additional_data(header)
        stream.write(header)

    def tell(self):
        return self.position

    def write(self, data):
        self.stream.write(self.encryptor.update(bytes(data)))
        self.position += len(data)
        return len(data)

    def flush(self):
        self.stream.flush()

    def finish(self):
        self.stream.write(self.encryptor.finalize())
        self.stream.write(self.encryptor.tag)
        self.stream.flush()
        os.fsync(self.stream.fileno())


def backup_media(database, settings, storage_factory, destination=None):
    key = encryption_key(settings.memory_backup_key)
    folder = Path(destination or settings.memory_backup_dir or '')
    if not (destination or settings.memory_backup_dir) or not folder.is_absolute() or not folder.is_dir():
        raise MediaError('backup_destination', '请指定已存在的绝对备份目录，优先使用外置硬盘或NAS')
    # Do not silently put the only backup next to the source or in its Git tree.
    from app.core.config import ROOT
    if folder.resolve().is_relative_to(ROOT.resolve()):
        raise MediaError('backup_destination', '备份目录必须位于项目目录之外')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target = folder / f'memory-{stamp}-{uuid4().hex[:8]}.acmedia'
    partial = target.with_suffix('.acmedia.partial')
    try:
        with database.transaction() as db:
            # Dedicated transaction: snapshot rows together; block physical cleanup only.
            db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
            db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': BACKUP_LOCK})
            pairs = list(db.execute(select(MemoryAsset, MemoryObject).join(MemoryObject,
                MemoryObject.asset_id == MemoryAsset.id).where(MemoryAsset.deleted_at.is_(None),
                MemoryObject.state == 'active').order_by(MemoryAsset.id)).all())
            if len(pairs) > MAX_ENTRIES:
                raise MediaError('backup_limit', '单次图片备份超过10000张，请先扩展备份容量策略')
            rows = []
            for asset, obj in pairs:
                rows.append({'asset_id': str(asset.id), 'user_id': str(asset.user_id),
                    'version': asset.version, 'created_at': asset.created_at.isoformat(),
                    'object_id': str(obj.id), 'bucket': obj.bucket, 'object_path': obj.object_path,
                    'sha256': obj.sha256, 'byte_size': obj.byte_size, 'width': obj.width,
                    'height': obj.height, 'content_type': obj.content_type,
                    'file': 'objects/' + obj.object_path})
            revision = db.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
            if revision != [EXPECTED_REVISION]:
                raise MediaError('backup_revision', '数据库迁移版本不符，备份已停止')
            manifest = {'format': 'adventure-memory-media', 'version': 1,
                'revision': EXPECTED_REVISION, 'created_at': datetime.now(timezone.utc).isoformat(),
                'scope': 'current_active_images', 'assets': rows}
            encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()
            if len(encoded) > MAX_MANIFEST:
                raise MediaError('backup_limit', '备份清单超过容量限制')
            with partial.open('xb') as file:
                writer = EncryptedWriter(file, key)
                with ZipFile(writer, 'w', compression=ZIP_STORED) as archive:
                    archive.writestr('manifest.json', encoded)
                    checked = set()
                    for row in rows:
                        store = storage_factory(row['bucket'])
                        if row['bucket'] not in checked:
                            store.ensure_private()
                            checked.add(row['bucket'])
                        data = store.get(row['object_path'])
                        if len(data) != row['byte_size'] or sha256(data).hexdigest() != row['sha256']:
                            raise MediaError('backup_integrity', '源图片缺失或校验不符，未生成完成的备份')
                        archive.writestr(row['file'], data)
                writer.finish()
        partial.replace(target)
        return {'path': str(target), 'images': len(rows), 'independent_copy_verified': False}
    except Exception:
        partial.unlink(missing_ok=True)
        raise


@contextmanager
def open_backup(path, secret):
    key = encryption_key(secret)
    # TemporaryFile is deleted on close, even if validation fails. Never extract ZIP paths.
    with Path(path).open('rb') as source, tempfile.TemporaryFile() as plain:
        header = source.read(len(MAGIC) + 12)
        if len(header) != len(MAGIC) + 12 or not header.startswith(MAGIC):
            raise MediaError('backup_format', '不是受支持的图片备份文件')
        size = source.seek(0, 2)
        remaining = size - len(header) - 16
        if remaining < 0:
            raise MediaError('backup_format', '备份文件不完整')
        source.seek(-16, 2)
        tag = source.read(16)
        source.seek(len(header))
        decryptor = Cipher(algorithms.AES(key), modes.GCM(header[-12:], tag)).decryptor()
        decryptor.authenticate_additional_data(header)
        try:
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise MediaError('backup_format', '备份文件不完整')
                remaining -= len(chunk)
                plain.write(decryptor.update(chunk))
            plain.write(decryptor.finalize())
        except InvalidTag:
            raise MediaError('backup_integrity', '备份密钥错误或备份文件已损坏，未执行恢复') from None
        plain.seek(0)
        try:
            with ZipFile(plain) as archive:
                manifest = validate_archive(archive)
                yield archive, manifest
        except (BadZipFile, KeyError, ValueError, TypeError, UnicodeError):
            raise MediaError('backup_format', '备份清单或图片结构无效，未完成恢复') from None


def validate_archive(archive):
    entries = archive.infolist()
    if len(entries) > MAX_ENTRIES + 1 or len({x.filename for x in entries}) != len(entries):
        raise MediaError('backup_format', '备份条目重复或超出限制')
    if archive.getinfo('manifest.json').file_size > MAX_MANIFEST:
        raise MediaError('backup_format', '备份清单过大')
    manifest = json.loads(archive.read('manifest.json'))
    if (manifest.get('format') != 'adventure-memory-media' or manifest.get('version') != 1 or
            manifest.get('revision') not in SUPPORTED_MEDIA_REVISIONS or manifest.get('scope') != 'current_active_images' or
            not isinstance(manifest.get('assets'), list)):
        raise MediaError('backup_version', '备份格式或数据库版本不兼容')
    files, asset_ids = {'manifest.json'}, set()
    for row in manifest['assets']:
        owner = str(UUID(row['user_id']))
        asset_id = str(UUID(row['asset_id']))
        object_id = str(UUID(row['object_id']))
        path = validate_object_path(row['object_path'])
        validate_bucket(row['bucket'])
        if (not path.startswith(owner + '/') or path != f'{owner}/{object_id}.webp' or
                row['file'] != 'objects/' + path or row['file'] in files or asset_id in asset_ids or
                type(row['version']) is not int or row['version'] < 1 or
                type(row['byte_size']) is not int or not 0 < row['byte_size'] <= MAX_BYTES or
                type(row['width']) is not int or type(row['height']) is not int or
                not 0 < row['width'] * row['height'] <= 12_000_000 or row['width'] <= 0 or row['height'] <= 0 or
                row['content_type'] != 'image/webp'):
            raise MediaError('backup_format', '备份中的图片归属、路径或元数据无效')
        info = archive.getinfo(row['file'])
        if info.file_size != row['byte_size'] or info.compress_type != ZIP_STORED:
            raise MediaError('backup_integrity', '备份图片大小或编码不符')
        data = archive.read(row['file'])
        if sha256(data).hexdigest() != row['sha256']:
            raise MediaError('backup_integrity', '备份图片校验失败')
        files.add(row['file'])
        asset_ids.add(asset_id)
    if files != set(archive.namelist()):
        raise MediaError('backup_format', '备份含有未登记文件')
    return manifest


def restore_media(path, secret, storage, *, create_bucket=False):
    with open_backup(path, secret) as (archive, manifest):
        # Validate the entire archive before any cloud write or bucket creation.
        if any(row['bucket'] == storage.bucket for row in manifest['assets']):
            raise MediaError('restore_target', '请使用独立的空测试Bucket，禁止覆盖来源Bucket')
        storage.ensure_private(create=create_bucket)
        if not storage.is_empty():
            raise MediaError('restore_target', '恢复目标必须为空，不覆盖已有图片')
        for row in manifest['assets']:
            storage.put(row['object_path'], archive.read(row['file']))
        for row in manifest['assets']:
            data = storage.get(row['object_path'])
            if len(data) != row['byte_size'] or sha256(data).hexdigest() != row['sha256']:
                raise MediaError('restore_integrity', '恢复后云端图片校验失败，请保留备份并检查目标Bucket')
        return {'restored': len(manifest['assets']), 'verified': True,
            'database_changed': False, 'target_bucket': storage.bucket}
