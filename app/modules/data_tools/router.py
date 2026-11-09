from uuid import uuid4
from fastapi import APIRouter, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text
from app.core.config import ROOT
from app.modules.identity.service import current_user
from app.modules.quests.router import back, same_origin
from app.modules.quests.models import MainQuest, Milestone
from app.modules.tasks.models import Task
from app.modules.activity.models import ActivityLog
from app.modules.data_tools.service import export_snapshot

router=APIRouter()
templates=Jinja2Templates(directory=ROOT/'app/templates')

@router.get('/data')
def data_page(request:Request):
    from app.main import PAGES
    with request.app.state.database.transaction() as db:
        user=current_user(db,request.cookies.get('camp_session'))
        if not user: return back('/account')
        quests=list(db.scalars(select(MainQuest).where(MainQuest.user_id==user.id,MainQuest.deleted_at.is_not(None))))
        milestones=list(db.scalars(select(Milestone).where(Milestone.user_id==user.id,Milestone.deleted_at.is_not(None))))
        tasks=list(db.scalars(select(Task).where(Task.user_id==user.id,Task.deleted_at.is_not(None))))
        logs=list(db.scalars(select(ActivityLog).where(ActivityLog.user_id==user.id,ActivityLog.deleted_at.is_not(None))))
        available=set(db.scalars(select(MainQuest.id).where(MainQuest.user_id==user.id,MainQuest.deleted_at.is_(None))))
        return templates.TemplateResponse(request=request,name='data.html',context={'app_name':request.app.state.settings.app_name,'pages':PAGES,'page':'data','current':PAGES['data'],'quests':quests,'milestones':milestones,'tasks':tasks,'logs':logs,'available':available,'request_id':uuid4})

@router.post('/data/export')
def export(request:Request):
    same_origin(request)
    with request.app.state.database.transaction() as db:
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        user=current_user(db,request.cookies.get('camp_session'))
        if not user: return back('/account')
        payload=export_snapshot(db,user)
    return Response(payload,media_type='application/zip',headers={'Content-Disposition':'attachment; filename="adventure-camp-export.zip"','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
