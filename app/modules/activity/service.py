"""Server-authoritative focus timer commands; caller owns the transaction."""
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
from sqlalchemy import select
from app.modules.identity.service import lock_user
from app.modules.tasks.service import get_task, ensure_available
from app.modules.activity.models import FocusSession, FocusSegment, ActivityLog


def active(db, user_id):
    return db.scalar(select(FocusSession).where(FocusSession.user_id == user_id, FocusSession.status.in_(['running','paused'])))


def duration(session, now):
    value = session.accumulated_seconds
    if session.status == 'running' and session.resumed_at:
        value += max(0, int((now - session.resumed_at).total_seconds()))
    return min(value, session.target_seconds) if session.mode == 'countdown' else value


def start(db, user_id: UUID, mode: str, minutes: str, task_id: UUID | None, request_id: UUID):
    lock_user(db, user_id)
    existing = db.get(FocusSession, request_id)
    if existing:
        same_minutes = mode != 'countdown' or (minutes.isdigit() and int(minutes) * 60 == existing.target_seconds)
        if existing.user_id != user_id or existing.mode != mode or existing.task_id != task_id or not same_minutes:
            raise ValueError('提交编号已用于其他计时，请刷新页面')
        return existing
    if active(db, user_id):
        raise ValueError('已有进行中或暂停的计时，请先结束')
    if mode not in ('elapsed','countdown'):
        raise ValueError('计时模式无效')
    target = None
    if mode == 'countdown':
        try:
            target = int(minutes) * 60
        except (ValueError, TypeError):
            raise ValueError('请输入 1–720 分钟') from None
        if not 60 <= target <= 43200:
            raise ValueError('请输入 1–720 分钟')
    if task_id:
        task = get_task(db, user_id, task_id)
        ensure_available(db, task)
        if task.status == 'completed':
            raise ValueError('已完成任务不能开始计时')
    now = datetime.now(timezone.utc)
    session = FocusSession(id=request_id, user_id=user_id, task_id=task_id, status='running', mode=mode,
                           target_seconds=target, accumulated_seconds=0, started_at=now, resumed_at=now)
    db.add(session)
    db.flush()
    db.add(FocusSegment(id=uuid4(), user_id=user_id, session_id=session.id, started_at=now))
    return session


def transition(db, user_id: UUID, session_id: UUID, action: str, confirmed_seconds: int | None = None):
    lock_user(db, user_id)
    session = db.scalar(select(FocusSession).where(FocusSession.id == session_id, FocusSession.user_id == user_id).execution_options(populate_existing=True))
    if not session:
        raise ValueError('计时不存在')
    if action == 'finish' and session.status == 'finished':
        return session
    if action == 'finish' and confirmed_seconds is not None:
        available = duration(session, datetime.now(timezone.utc))
        if not 0 <= confirmed_seconds <= available:
            raise ValueError('确认的有效时长不能大于计时记录，也不能小于零')
    if action == 'pause' and session.status == 'paused':
        return session
    if action == 'resume' and session.status == 'running':
        return session
    if session.status == 'finished' or action not in ('pause','resume','finish'):
        raise ValueError('计时状态不能执行此操作')
    now = datetime.now(timezone.utc)
    if session.status == 'running' and action in ('pause','finish'):
        total = duration(session, now)
        segment = db.scalar(select(FocusSegment).where(FocusSegment.session_id == session.id, FocusSegment.user_id == user_id, FocusSegment.ended_at.is_(None)))
        if not segment:
            raise ValueError('计时区间缺失')
        seconds = total - session.accumulated_seconds
        segment.ended_at = session.resumed_at + timedelta(seconds=seconds)
        session.accumulated_seconds = total
        session.resumed_at = None
    if action == 'pause':
        session.status = 'paused'
    elif action == 'resume':
        session.status = 'running'
        session.resumed_at = now
        db.add(FocusSegment(id=uuid4(), user_id=user_id, session_id=session.id, started_at=now))
    else:
        session.status = 'finished'
        session.ended_at = now
        actual = session.accumulated_seconds if confirmed_seconds is None else confirmed_seconds
        note = '' if confirmed_seconds is None else f'用户确认有效时长；原计时 {session.accumulated_seconds} 秒'
        db.add(ActivityLog(id=uuid4(), user_id=user_id, task_id=session.task_id, session_id=session.id,
                           occurred_at=session.started_at, duration_seconds=actual, category='', note=note))
    db.flush()
    return session
