"""Export a consistent, owner-scoped snapshot without credentials."""
import csv
import io
import json
from datetime import date, datetime, timezone
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile
from sqlalchemy import inspect, select
from app.modules.quests.models import MainQuest, Milestone, QuestEvent
from app.modules.tasks.models import Task, TaskEvent
from app.modules.activity.models import ActivityLog, ActivityEvent, FocusSession, FocusSegment
from app.modules.growth.models import RewardEntry, RewardSettings

from app.modules.startup_items.models import StartupItem

MODELS=(MainQuest,Milestone,QuestEvent,Task,TaskEvent,FocusSession,FocusSegment,ActivityLog,ActivityEvent,RewardSettings,RewardEntry,StartupItem)

def scalar(value):
    if isinstance(value,(UUID,datetime,date)): return value.isoformat() if hasattr(value,'isoformat') else str(value)
    return value

def export_snapshot(db,user):
    data={'format':'adventure-camp-export','version':1,'exported_at':datetime.now(timezone.utc).isoformat(),
          'profile':{'id':str(user.id),'username':user.username,'display_name':user.display_name,'timezone':user.timezone},'tables':{}}
    for model in MODELS:
        columns=[c.key for c in inspect(model).column_attrs]
        records=db.scalars(select(model).where(model.user_id==user.id)).all()
        data['tables'][model.__tablename__]=[{name:scalar(getattr(item,name)) for name in columns} for item in records]
    buf=io.BytesIO()
    with ZipFile(buf,'w',ZIP_DEFLATED) as archive:
        archive.writestr('adventure-camp.json',json.dumps(data,ensure_ascii=False,indent=2))
        for model in MODELS:
            columns=[c.key for c in inspect(model).column_attrs]
            file=io.StringIO(newline=''); writer=csv.DictWriter(file,fieldnames=columns); writer.writeheader()
            for row in data['tables'][model.__tablename__]:
                writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})
            archive.writestr('csv/'+model.__tablename__+'.csv',file.getvalue().encode('utf-8-sig'))
        archive.writestr('README.txt','Adventure Camp data export v1. Includes deleted records. JSON is a data export; automatic import/restore is not provided. Keep this file private.\n')
    return buf.getvalue()
