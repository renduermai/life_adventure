"""Compose the homepage from user-owned domain facts."""
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.modules.quests.models import MainQuest, Milestone
from app.modules.quests.service import quest_progress
from app.modules.tasks.models import Task
from app.modules.tasks.service import unavailable_reasons
from app.modules.activity.models import ActivityLog
from app.modules.growth.service import balances, level


def dashboard(db, user, now=None):
    zone=ZoneInfo(user.timezone)
    today=(now or datetime.now(zone)).astimezone(zone).date()
    quests=list(db.scalars(select(MainQuest).where(MainQuest.user_id==user.id, MainQuest.deleted_at.is_(None), MainQuest.status=='active').order_by(MainQuest.created_at.desc()).limit(5)))
    milestones=list(db.scalars(select(Milestone).where(Milestone.user_id==user.id, Milestone.main_quest_id.in_([q.id for q in quests]))))
    progress={q.id:quest_progress(db,user.id,q.id,[m for m in milestones if m.main_quest_id==q.id]) for q in quests}
    candidates=list(db.scalars(select(Task).where(Task.user_id==user.id,Task.deleted_at.is_(None),Task.status.in_(['todo','in_progress']),Task.due_date.is_not(None),Task.due_date<=today).order_by(Task.due_date,Task.created_at)))
    blocked=unavailable_reasons(db,user.id,candidates)
    tasks=[t for t in candidates if t.id not in blocked][:8]
    logs=list(db.scalars(select(ActivityLog).where(ActivityLog.user_id==user.id,ActivityLog.deleted_at.is_(None)).order_by(ActivityLog.occurred_at.desc()).limit(5)))
    xp,coins=balances(db,user.id)
    return dict(quests=quests,progress=progress,tasks=tasks,logs=logs,xp=xp,coins=coins,level=level(xp),today=today,zone=zone)
