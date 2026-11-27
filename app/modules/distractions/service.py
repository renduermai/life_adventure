import hashlib
from datetime import datetime, timezone
from sqlalchemy import select
from app.modules.ai_gateway.security import AIError
from app.modules.identity.service import lock_user
from app.modules.distractions.models import DistractionNote


def public(note):
    return {key: getattr(note, key) for key in ('id', 'content', 'version', 'created_at', 'updated_at')}


def listing(db, uid, offset=0):
    rows = list(db.scalars(select(DistractionNote).where(DistractionNote.user_id == uid,
        DistractionNote.deleted_at.is_(None)).order_by(DistractionNote.created_at.desc(),
        DistractionNote.id.desc()).offset(offset).limit(21)))
    return {'items': [public(note) for note in rows[:20]], 'next_offset': offset + 20 if len(rows) > 20 else None}


def get(db, uid, note_id):
    note = db.scalar(select(DistractionNote).where(DistractionNote.id == note_id,
        DistractionNote.user_id == uid, DistractionNote.deleted_at.is_(None)))
    if note is None:
        raise AIError('not_found', '杂念不存在或已删除', 404)
    return note


def create(db, uid, data):
    lock_user(db, uid)
    fingerprint = hashlib.sha256(data.content.encode('utf-8')).hexdigest()
    old = db.scalar(select(DistractionNote).where(DistractionNote.user_id == uid,
        DistractionNote.create_request_id == data.request_id))
    if old is not None:
        if old.create_fingerprint != fingerprint:
            raise AIError('request_conflict', '保存编号已用于其他内容，请重新提交', 409)
        if old.deleted_at is not None:
            raise AIError('deleted_request', '原记录已删除，请使用新的保存编号', 409)
        return public(old)
    note = DistractionNote(user_id=uid, content=data.content, create_request_id=data.request_id,
        create_fingerprint=fingerprint)
    db.add(note)
    db.flush()
    return public(note)


def delete(db, uid, note_id, data):
    lock_user(db, uid)
    note = get(db, uid, note_id)
    if note.version != data.expected_version:
        raise AIError('version_conflict', '记录版本已变化，请重新读取', 409)
    note.deleted_at = datetime.now(timezone.utc)
    note.version += 1
    db.flush()
    return {'deleted': True, 'id': note.id}
