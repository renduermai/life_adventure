import hashlib
from datetime import datetime, timezone
from sqlalchemy import select
from app.modules.ai_gateway.security import AIError
from app.modules.identity.service import lock_user
from app.modules.startup_items.models import StartupItem
from app.modules.startup_items.schemas import ItemFields


def public(item):
    return {name: getattr(item, name) for name in (
        'id', 'description', 'importance', 'urgency', 'progress', 'version', 'created_at', 'updated_at')}


def listing(db, uid, offset):
    rows = list(db.scalars(select(StartupItem).where(StartupItem.user_id == uid,
        StartupItem.deleted_at.is_(None)).order_by(StartupItem.created_at.desc(), StartupItem.id.desc()).offset(offset).limit(21)))
    return {'items': [public(item) for item in rows[:20]], 'next_offset': offset + 20 if len(rows) > 20 else None}


def get(db, uid, item_id):
    item = db.scalar(select(StartupItem).where(StartupItem.id == item_id,
        StartupItem.user_id == uid, StartupItem.deleted_at.is_(None)))
    if not item:
        raise AIError('not_found', '事项不存在或已删除', 404)
    return item


def create(db, uid, data):
    lock_user(db, uid)
    fields = ItemFields.model_validate(data.model_dump(include=set(ItemFields.model_fields)))
    fingerprint = hashlib.sha256(fields.model_dump_json().encode()).hexdigest()
    old = db.scalar(select(StartupItem).where(StartupItem.user_id == uid, StartupItem.create_request_id == data.request_id))
    if old:
        if old.create_fingerprint != fingerprint:
            raise AIError('request_conflict', '保存编号已用于其他内容，请重新提交', 409)
        if old.deleted_at:
            raise AIError('not_found', '此事项已删除，请重新新增', 409)
        return public(old)
    item = StartupItem(user_id=uid, create_request_id=data.request_id,
        create_fingerprint=fingerprint, **fields.model_dump())
    db.add(item)
    db.flush()
    return public(item)


def mutate(db, uid, item_id, data, delete=False):
    lock_user(db, uid)
    item = get(db, uid, item_id)
    if item.version != data.expected_version:
        raise AIError('version_conflict', '事项已在其他页面修改，请重新读取后再操作', 409)
    if delete:
        item.deleted_at = datetime.now(timezone.utc)
    else:
        for field in ItemFields.model_fields:
            setattr(item, field, getattr(data, field))
    item.version += 1
    db.flush()
    return {'deleted': True, 'id': item.id} if delete else public(item)
