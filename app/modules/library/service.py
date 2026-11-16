import hashlib
import json
from datetime import datetime, timezone
from sqlalchemy import select, or_
from fastapi import HTTPException
from app.modules.identity.service import lock_user
from app.modules.quests.models import MainQuest
from app.modules.tasks.models import Task
from app.modules.tasks.service import unavailable_reasons
from app.modules.library.models import LibraryLink


def targets(db, uid):
    quests = list(db.scalars(select(MainQuest).where(MainQuest.user_id==uid, MainQuest.deleted_at.is_(None)).order_by(MainQuest.title, MainQuest.id)))
    tasks = list(db.scalars(select(Task).where(Task.user_id==uid, Task.deleted_at.is_(None)).order_by(Task.title, Task.id)))
    blocked = unavailable_reasons(db,uid,tasks)
    return {'quests':[{ 'id':q.id,'title':q.title} for q in quests],
            'tasks':[{ 'id':t.id,'title':t.title} for t in tasks if t.id not in blocked]}


def validate_target(db, uid, quest_id, task_id):
    if (quest_id is None)==(task_id is None):
        raise HTTPException(422,'必须且只能关联一个任务')
    choices=targets(db,uid)
    rows=choices['quests' if quest_id else 'tasks']
    if not any(row['id']==(quest_id or task_id) for row in rows):
        raise HTTPException(404,'关联任务不存在、已删除或不可用')


def public(link, choices):
    rows=choices['quests' if link.main_quest_id else 'tasks']
    title=next((row['title'] for row in rows if row['id']==(link.main_quest_id or link.task_id)),None)
    return {key:getattr(link,key) for key in ('id','description','url','main_quest_id','task_id','click_count','version','created_at','updated_at')} | {'target_title':title, 'target_available':title is not None}


def listing(db,uid,offset=0,quest_id=None,task_id=None):
    if quest_id is not None or task_id is not None: validate_target(db,uid,quest_id,task_id)
    choices=targets(db,uid)
    query=select(LibraryLink).where(LibraryLink.user_id==uid,LibraryLink.deleted_at.is_(None),or_(
        LibraryLink.main_quest_id.in_([q['id'] for q in choices['quests']]),
        LibraryLink.task_id.in_([t['id'] for t in choices['tasks']])))
    if quest_id: query=query.where(LibraryLink.main_quest_id==quest_id)
    if task_id: query=query.where(LibraryLink.task_id==task_id)
    rows=list(db.scalars(query.order_by(LibraryLink.click_count.desc(),LibraryLink.created_at.desc(),LibraryLink.id.desc()).offset(offset).limit(21)))
    return {'items':[public(row,choices) for row in rows[:20]],'next_offset':offset+20 if len(rows)>20 else None}


def get(db,uid,link_id):
    row=db.scalar(select(LibraryLink).where(LibraryLink.id==link_id,LibraryLink.user_id==uid,LibraryLink.deleted_at.is_(None)))
    if row is None: raise HTTPException(404,'链接不存在或已删除')
    return row


def create(db,uid,data):
    lock_user(db,uid)
    fp=hashlib.sha256(json.dumps(data.model_dump(mode='json',exclude={'request_id'}),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    old=db.scalar(select(LibraryLink).where(LibraryLink.user_id==uid,LibraryLink.create_request_id==data.request_id))
    if old:
        if old.create_fingerprint!=fp: raise HTTPException(409,'提交编号已用于其他内容')
        if old.deleted_at: raise HTTPException(409,'该链接已删除，请重新新增')
        return public(old,targets(db,uid))
    validate_target(db,uid,data.main_quest_id,data.task_id)
    row=LibraryLink(user_id=uid,create_request_id=data.request_id,create_fingerprint=fp,**data.model_dump(exclude={'request_id'}))
    db.add(row);db.flush()
    return public(row,targets(db,uid))


def mutate(db,uid,link_id,data,delete=False):
    lock_user(db,uid)
    row=get(db,uid,link_id)
    if row.version!=data.expected_version: raise HTTPException(409,'记录已变化，请重新读取')
    if delete: row.deleted_at=datetime.now(timezone.utc)
    else:
        validate_target(db,uid,data.main_quest_id,data.task_id)
        row.main_quest_id,row.task_id=data.main_quest_id,data.task_id
    row.version+=1;db.flush()
    return {'deleted':True,'id':row.id} if delete else public(row,targets(db,uid))
