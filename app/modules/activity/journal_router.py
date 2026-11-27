"""Authenticated time journal pages."""
from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from app.core.config import ROOT
from app.modules.identity.service import current_user
from app.modules.quests.router import same_origin, back
from app.modules.activity import journal
from app.modules.activity.models import ActivityEvent
from app.modules.tasks.models import Task

router=APIRouter()
templates=Jinja2Templates(directory=ROOT / 'app/templates')

def render(request,view,status_code=200,**values):
    from app.main import PAGES
    return templates.TemplateResponse(request=request,name='journal.html',status_code=status_code,context={'view':view,'app_name':request.app.state.settings.app_name,'pages':PAGES,'page':'journal','current':PAGES['journal'],**values})

def tasks_for(db,user_id):
    return list(db.scalars(select(Task).where(Task.user_id==user_id).order_by(Task.title)))

@router.get('/journal')
def list_page(request: Request, period: str='week', day: str='', category: str='', task: str='', deleted: bool=False):
    try:
        with request.app.state.database.transaction() as db:
            user=current_user(db,request.cookies.get('camp_session'))
            if not user: return back('/account')
            if len(category)>60: raise ValueError('分类过长')
            task_id=UUID(task) if task else None
            start,end,first,last=journal.period(period,day,user.timezone)
            logs=journal.list_logs(db,user.id,start,end,category,task_id,deleted)
            task_items=tasks_for(db,user.id)
            titles={t.id:t.title + ('（已删除）' if t.deleted_at else '') for t in task_items}
            grouped={}
            for item in logs:
                grouped[item.task_id]=grouped.get(item.task_id,0)+item.duration_seconds
            zone=ZoneInfo(user.timezone)
            return render(request,'list',logs=logs,period=period,day=day or datetime.now(zone).date().isoformat(),category=category,selected_task=task,deleted=deleted,first=first,last=last,total=sum(x.duration_seconds for x in logs),grouped=grouped,titles=titles,tasks=task_items,zone=zone,request_id=uuid4(),now=datetime.now(zone).strftime('%Y-%m-%dT%H:%M'))
    except ValueError as error:
        return render(request,'error',status_code=400,error=str(error))

@router.get('/journal/{log_id}')
def detail(request: Request,log_id: UUID):
    try:
        with request.app.state.database.transaction() as db:
            user=current_user(db,request.cookies.get('camp_session'))
            if not user: return back('/account')
            item=journal.get_log(db,user.id,log_id)
            events=list(db.scalars(select(ActivityEvent).where(ActivityEvent.user_id==user.id,ActivityEvent.activity_id==item.id).order_by(ActivityEvent.created_at.desc(),ActivityEvent.id.desc())))
            zone=ZoneInfo(user.timezone)
            return render(request,'detail',item=item,events=events,tasks=tasks_for(db,user.id),local_time=item.occurred_at.astimezone(zone).strftime('%Y-%m-%dT%H:%M:%S'),zone=zone)
    except ValueError as error:
        return render(request,'error',status_code=404,error=str(error))

def mutate(request,action,form,log_id=None):
    try:
        with request.app.state.database.transaction() as db:
            user=current_user(db,request.cookies.get('camp_session'))
            if not user: return back('/account')
            data={key:str(form.get(key,'')) for key in ('occurred_at','duration_seconds','category','note','task_id')}
            if action=='create':
                item=journal.create(db,user.id,UUID(str(form['request_id'])),data)
            else:
                item=journal.change(db,user.id,log_id,int(str(form['version'])),action,data)
            return back('/journal' if action=='delete' else f'/journal/{item.id}')
    except (ValueError,KeyError,TypeError) as error:
        return render(request,'error',status_code=400,error=str(error) if isinstance(error,ValueError) else '输入不完整')

@router.post('/journal/create')
async def create(request:Request):
    same_origin(request)
    return await run_in_threadpool(mutate,request,'create',await request.form())

@router.post('/journal/{log_id}/{action}')
async def update(request:Request,log_id:UUID,action:str):
    same_origin(request)
    if action not in ('edit','delete','restore'): return render(request,'error',status_code=404,error='操作不存在')
    return await run_in_threadpool(mutate,request,action,await request.form(),log_id)
