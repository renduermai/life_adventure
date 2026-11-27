"""Time journal commands, user-local date boundaries and summaries."""
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.modules.activity.models import ActivityLog, ActivityEvent
from app.modules.identity.service import lock_user
from app.modules.tasks.service import get_task, ensure_available


def local_datetime(value, zone):
    try:
        naive = datetime.fromisoformat(value)
        if naive.tzinfo is not None:
            raise ValueError()
        aware = naive.replace(tzinfo=ZoneInfo(zone))
        if aware.astimezone(timezone.utc).astimezone(ZoneInfo(zone)).replace(tzinfo=None) != naive:
            raise ValueError()
        return aware.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ValueError('请输入有效的本地日期和时间') from None


def period(kind, day, zone):
    try:
        d = date.fromisoformat(day) if day else datetime.now(ZoneInfo(zone)).date()
        if kind == 'day':
            start, end = d, d + timedelta(days=1)
        elif kind == 'week':
            start = d - timedelta(days=d.weekday())
            end = start + timedelta(days=7)
        elif kind == 'month':
            start = d.replace(day=1)
            end = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
        else:
            raise ValueError()
        z = ZoneInfo(zone)
        return (datetime.combine(start,time.min,z).astimezone(timezone.utc), datetime.combine(end,time.min,z).astimezone(timezone.utc), start, end)
    except (ValueError, OverflowError):
        raise ValueError('日期或查询范围无效') from None


def fields(data, zone):
    try:
        seconds = int(str(data.get('duration_seconds', '')))
    except ValueError:
        raise ValueError('时长须为整数秒') from None
    if not 0 <= seconds <= 604800:
        raise ValueError('时长须为 0–604800 秒')
    category, note = str(data.get('category','')).strip(), str(data.get('note','')).strip()
    if len(category) > 60 or len(note) > 5000:
        raise ValueError('分类最多 60 字，内容最多 5000 字')
    try:
        task = UUID(str(data['task_id'])) if data.get('task_id') else None
    except ValueError:
        raise ValueError('关联副本无效') from None
    return dict(occurred_at=local_datetime(str(data.get('occurred_at','')),zone), duration_seconds=seconds, category=category, note=note, task_id=task)


def snapshot(item):
    return {key: str(value) if isinstance(value,(UUID,datetime)) else value for key in ('task_id','occurred_at','duration_seconds','category','note','deleted_at') for value in [getattr(item,key)]}


def record_event(db, item, action, payload):
    db.add(ActivityEvent(user_id=item.user_id, activity_id=item.id, action=action, payload=payload))


def get_log(db, user_id, log_id):
    item = db.scalar(select(ActivityLog).where(ActivityLog.user_id==user_id, ActivityLog.id==log_id).execution_options(populate_existing=True))
    if item is None:
        raise ValueError('记录不存在或无权访问')
    return item


def create(db, user_id, request_id, data):
    user = lock_user(db,user_id)
    values = fields(data,user.timezone)
    existing = db.get(ActivityLog,request_id)
    if existing:
        if existing.user_id != user_id or existing.session_id is not None or any(getattr(existing,k) != v for k,v in values.items()):
            raise ValueError('提交编号已使用，请刷新后重试')
        return existing
    if values['task_id']:
        ensure_available(db,get_task(db,user_id,values['task_id']))
    item = ActivityLog(id=request_id,user_id=user_id,**values)
    db.add(item); db.flush()
    record_event(db,item,'created',{'after':snapshot(item)})
    return item


def change(db,user_id,log_id,version,action,data):
    user=lock_user(db,user_id)
    item=get_log(db,user_id,log_id)
    if item.version != version:
        raise ValueError('记录已被修改，请刷新页面后重试')
    before=snapshot(item)
    if action=='edit':
        if item.deleted_at:
            raise ValueError('请先恢复记录')
        values=fields(data,user.timezone)
        if values['task_id'] and values['task_id'] != item.task_id:
            ensure_available(db,get_task(db,user_id,values['task_id']))
        for k,v in values.items(): setattr(item,k,v)
    elif action=='delete':
        if item.deleted_at: return item
        item.deleted_at=datetime.now(timezone.utc)
    elif action=='restore':
        if not item.deleted_at: return item
        item.deleted_at=None
    else:
        raise ValueError('操作无效')
    item.version += 1
    record_event(db,item,action,{'before':before,'after':snapshot(item)})
    db.flush()
    return item


def list_logs(db,user_id,start,end,category='',task_id=None,deleted=False):
    query=select(ActivityLog).where(ActivityLog.user_id==user_id, ActivityLog.occurred_at>=start, ActivityLog.occurred_at<end, ActivityLog.deleted_at.is_not(None) if deleted else ActivityLog.deleted_at.is_(None))
    if category: query=query.where(ActivityLog.category==category)
    if task_id: query=query.where(ActivityLog.task_id==task_id)
    return list(db.scalars(query.order_by(ActivityLog.occurred_at.desc(),ActivityLog.id)))
