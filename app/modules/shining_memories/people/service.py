from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from sqlalchemy import select,func
from app.modules.identity.service import lock_user
from app.modules.identity.models import User
from ..shared.images import MediaError
from .models import MemoryPerson,MemoryPersonEvent


def now():return datetime.now(timezone.utc)


def today(db,uid):return now().astimezone(ZoneInfo(db.get(User,uid).timezone)).date()


def fingerprint(data):return sha256(json.dumps(data,sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()


def get(db,uid,pid):
    person=db.scalar(select(MemoryPerson).where(MemoryPerson.id==pid,MemoryPerson.user_id==uid,MemoryPerson.deleted_at.is_(None)))
    if not person:raise MediaError('not_found','人物不存在或无权访问',404)
    return person


def check_date(value,current):
    if value and value>current:raise MediaError('future_date','联系或事件日期不能晚于今天')


def heat(contact,current):
    if contact is None:return None
    days=max(0,(current-contact).days)
    return int(max(Decimal(0),Decimal(100)*(1-Decimal(days)/1095)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))


def contact_date(db,person):
    actual=db.scalar(select(func.max(MemoryPersonEvent.event_date)).where(MemoryPersonEvent.person_id==person.id,
        MemoryPersonEvent.user_id==person.user_id,MemoryPersonEvent.deleted_at.is_(None),MemoryPersonEvent.is_actual_contact.is_(True)))
    return max([d for d in (person.manual_contact_date,actual) if d],default=None)


def public(db,person,current):
    result={k:getattr(person,k) for k in ('id','name','relationship','precious_moments','manual_contact_date','contact_preference','notes','version','created_at','updated_at')}
    contact=contact_date(db,person)
    return result|{'last_contact_date':contact,'contact_heat':heat(contact,current)}


def listing(db,uid,offset=0):
    rows=list(db.scalars(select(MemoryPerson).where(MemoryPerson.user_id==uid,MemoryPerson.deleted_at.is_(None))
        .order_by(MemoryPerson.created_at.desc(),MemoryPerson.id)))
    from .analysis import view
    values=[]
    for p in rows:
        value=public(db,p,today(db,uid));status=view(db,uid,p.id)
        values.append(value|{'recommendation':status['recommendation'],'analysis_stale':status.get('stale',False),
            'meaning_label':status['analysis']['meaning_label'] if status.get('analysis') else None})
    def order(p):
        r=p['recommendation'];group=0 if r['score'] is not None else 2 if r['status'] in {'excluded','deferred'} else 1
        return (group,-(r['score'] or 0),str(p['id']))
    values.sort(key=order)
    return {'items':values[offset:offset+20],'next_offset':offset+20 if len(values)>offset+20 else None}


def create(db,uid,data):
    lock_user(db,uid);values=data.model_dump(exclude={'request_id'});fp=fingerprint(values)
    old=db.scalar(select(MemoryPerson).where(MemoryPerson.user_id==uid,MemoryPerson.create_request_id==data.request_id))
    if old:
        if old.create_fingerprint!=fp or old.deleted_at:raise MediaError('request_conflict','保存编号已被使用',409)
        return public(db,old,today(db,uid))
    check_date(data.manual_contact_date,today(db,uid))
    person=MemoryPerson(user_id=uid,create_request_id=data.request_id,create_fingerprint=fp,**values)
    db.add(person);db.flush();return public(db,person,today(db,uid))


def mutate(db,uid,pid,data,delete=False):
    lock_user(db,uid);p=get(db,uid,pid)
    if p.version!=data.expected_version:raise MediaError('version_conflict','人物已变化，请重新读取',409)
    if delete:p.deleted_at=now()
    else:
        check_date(data.manual_contact_date,today(db,uid))
        for k,v in data.model_dump(exclude={'expected_version'}).items():setattr(p,k,v)
    p.version+=1;p.updated_at=now();db.flush()
    return {'deleted':True} if delete else public(db,p,today(db,uid))


def event_public(row):return {k:getattr(row,k) for k in ('id','event_date','content','is_actual_contact','version','created_at')}


def events(db,uid,pid,offset=0):
    get(db,uid,pid)
    rows=list(db.scalars(select(MemoryPersonEvent).where(MemoryPersonEvent.person_id==pid,MemoryPersonEvent.user_id==uid,
        MemoryPersonEvent.deleted_at.is_(None)).order_by(MemoryPersonEvent.event_date.desc(),MemoryPersonEvent.created_at.desc(),MemoryPersonEvent.id).offset(offset).limit(21)))
    return {'items':[event_public(e) for e in rows[:20]],'next_offset':offset+20 if len(rows)>20 else None}


def save_event(db,uid,pid,data,eid=None,delete=False):
    lock_user(db,uid);p=get(db,uid,pid)
    if eid:
        row=db.scalar(select(MemoryPersonEvent).where(MemoryPersonEvent.id==eid,MemoryPersonEvent.person_id==pid,
            MemoryPersonEvent.user_id==uid,MemoryPersonEvent.deleted_at.is_(None)))
        if not row:raise MediaError('not_found','事件不存在或无权访问',404)
        if row.version!=data.expected_version:raise MediaError('version_conflict','事件已变化，请重新读取',409)
        if delete:row.deleted_at=now()
        else:
            check_date(data.event_date,today(db,uid))
            for k,v in data.model_dump(exclude={'expected_version'}).items():setattr(row,k,v)
        row.version+=1
    else:
        values=data.model_dump(exclude={'request_id'});fp=fingerprint(values|{'person_id':pid})
        row=db.scalar(select(MemoryPersonEvent).where(MemoryPersonEvent.user_id==uid,MemoryPersonEvent.create_request_id==data.request_id))
        if row:
            if row.create_fingerprint!=fp or row.deleted_at:raise MediaError('request_conflict','事件编号已被使用',409)
            return event_public(row)
        check_date(data.event_date,today(db,uid))
        row=MemoryPersonEvent(person_id=pid,user_id=uid,create_request_id=data.request_id,create_fingerprint=fp,**values);db.add(row)
    p.version+=1;p.updated_at=now();db.flush()
    return {'deleted':True} if delete else event_public(row)
