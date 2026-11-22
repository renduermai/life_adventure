"""Owner-scoped media lifecycle; cloud calls happen outside business transactions."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4
from sqlalchemy import select, text, or_
from app.modules.identity.service import lock_user
from .images import MediaError
from .models import MemoryAsset, MemoryObject

BACKUP_LOCK = 701132
RETENTION = timedelta(days=7)


def now():
    return datetime.now(timezone.utc)


def get_asset(db, uid, asset_id):
    row = db.scalar(select(MemoryAsset).where(MemoryAsset.id == asset_id,
        MemoryAsset.user_id == uid, MemoryAsset.deleted_at.is_(None)))
    if row is None:
        raise MediaError('not_found', '图片不存在或无权访问', 404)
    return row


def current_object(db, uid, asset_id):
    row = db.scalar(select(MemoryObject).where(MemoryObject.asset_id == asset_id,
        MemoryObject.user_id == uid, MemoryObject.state == 'active'))
    if row is None:
        raise MediaError('image_not_ready', '图片尚未成功上传或已删除', 404)
    return row


def public(asset, obj):
    return {'id': asset.id, 'version': asset.version, 'content_type': obj.content_type,
        'byte_size': obj.byte_size, 'width': obj.width, 'height': obj.height,
        'sha256': obj.sha256, 'url': '/api/shining-memories/assets/' + str(asset.id)}


def retire(obj, error=None):
    obj.state = 'retired'
    obj.error_code = error
    obj.delete_after = now() + RETENTION


def upload(database, storage, uid, image, request_id, asset_id=None, expected_version=None):
    fingerprint = sha256(f'{image.sha256}:{asset_id}:{expected_version}'.encode()).hexdigest()
    with database.transaction() as db:
        lock_user(db, uid)
        old = db.scalar(select(MemoryObject).where(MemoryObject.user_id == uid, MemoryObject.request_id == request_id))
        if old:
            if old.fingerprint != fingerprint:
                raise MediaError('request_conflict', '上传编号已用于其他图片或操作', 409)
            asset = get_asset(db, uid, old.asset_id)
            if old.state != 'active':
                raise MediaError('upload_processed', '该上传未就绪或已被替换；请重新读取，必要时使用新编号', 409)
            return public(asset, old)
        if asset_id:
            asset = get_asset(db, uid, asset_id)
            if asset.version != expected_version:
                raise MediaError('version_conflict', '图片已变化，请重新读取', 409)
            current_object(db, uid, asset.id)
        else:
            asset = MemoryAsset(user_id=uid, create_request_id=request_id, create_fingerprint=fingerprint)
            db.add(asset)
            db.flush()
        obj_id = uuid4()
        obj = MemoryObject(id=obj_id, asset_id=asset.id, user_id=uid, request_id=request_id,
            fingerprint=fingerprint, bucket=storage.bucket, object_path=f'{uid}/{obj_id}.webp',
            sha256=image.sha256, byte_size=len(image.data), width=image.width, height=image.height,
            content_type=image.content_type, state='pending')
        db.add(obj)
        db.flush()
        asset_id, object_path = asset.id, obj.object_path
    try:
        storage.ensure_private()
        storage.put(object_path, image.data)
        with database.transaction() as db:
            lock_user(db, uid)
            asset = get_asset(db, uid, asset_id)
            obj = db.get(MemoryObject, obj_id)
            if obj.state != 'pending' or (expected_version is not None and asset.version != expected_version):
                raise MediaError('version_conflict', '图片已变化，新上传未替换原图', 409)
            previous = db.scalar(select(MemoryObject).where(MemoryObject.asset_id == asset_id, MemoryObject.state == 'active'))
            if previous:
                retire(previous)
                db.flush()  # Release the partial unique index before activating the new revision.
                asset.version += 1
            obj.state = 'active'
            db.flush()
            return public(asset, obj)
    except Exception as error:
        # The pending reservation is committed before I/O, including ambiguous timeouts.
        # A process crash leaves a discoverable pending object for the cleanup command.
        with database.transaction() as db:
            lock_user(db, uid)
            obj = db.get(MemoryObject, obj_id)
            if obj and obj.state == 'pending':
                retire(obj, error.code if isinstance(error, MediaError) else 'publish_failed')
        if isinstance(error, MediaError):
            raise
        raise MediaError('upload_failed', '图片保存未完成，原图片保留；请重新读取', 503) from None


def read(database, storage_factory, uid, asset_id):
    with database.transaction() as db:
        asset = get_asset(db, uid, asset_id)
        obj = current_object(db, uid, asset_id)
        info, bucket, path = public(asset, obj), obj.bucket, obj.object_path
    storage = storage_factory(bucket)
    storage.ensure_private()
    data = storage.get(path)
    if len(data) != info['byte_size'] or sha256(data).hexdigest() != info['sha256']:
        raise MediaError('image_integrity', '云端图片校验失败，请从备份恢复', 502)
    return data, info


def delete(database, uid, asset_id, expected_version):
    with database.transaction() as db:
        lock_user(db, uid)
        from ..items.models import MemoryItem
        from ..wishes.models import MemoryWish
        if db.scalar(select(MemoryWish.id).where(MemoryWish.image_asset_id == asset_id, MemoryWish.user_id == uid, MemoryWish.deleted_at.is_(None))):
            raise MediaError('image_in_use', '图片已关联心愿，请先在心愿中替换或移除', 409)
        if db.scalar(select(MemoryItem.id).where(MemoryItem.image_asset_id == asset_id, MemoryItem.user_id == uid, MemoryItem.deleted_at.is_(None))):
            raise MediaError('image_in_use', '图片已关联物品，请先在物品中替换或移除', 409)
        asset = db.scalar(select(MemoryAsset).where(MemoryAsset.id == asset_id, MemoryAsset.user_id == uid))
        if asset is None:
            raise MediaError('not_found', '图片不存在或无权访问', 404)
        if asset.deleted_at:
            if asset.version == expected_version + 1:
                return {'deleted': True, 'cleanup_pending': True}
            raise MediaError('version_conflict', '图片已变化，请重新读取', 409)
        if asset.version != expected_version:
            raise MediaError('version_conflict', '图片已变化，请重新读取', 409)
        asset.deleted_at = now()
        asset.version += 1
        for obj in db.scalars(select(MemoryObject).where(MemoryObject.asset_id == asset_id,
                MemoryObject.state.in_(['pending', 'active']))):
            retire(obj)
        return {'deleted': True, 'cleanup_pending': True}


def cleanup(database, storage_factory):
    """Manual, retryable sweep; never deletes active or recently retired images."""
    removed, failed = 0, 0
    with database.transaction() as db:
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': BACKUP_LOCK})
        rows = list(db.scalars(select(MemoryObject).where(or_(
            (MemoryObject.state == 'retired') & (MemoryObject.delete_after <= now()),
            (MemoryObject.state == 'pending') & (MemoryObject.created_at < now() - RETENTION)))
            .order_by(MemoryObject.id).limit(100)))
        for obj in rows:
            try:
                storage = storage_factory(obj.bucket)
                storage.ensure_private()
                storage.delete(obj.object_path)
                obj.state, obj.error_code = 'deleted', None
                removed += 1
            except MediaError as error:
                obj.error_code = error.code
                failed += 1
    return {'removed': removed, 'failed': failed}
