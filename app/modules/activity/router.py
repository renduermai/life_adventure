from datetime import datetime, timezone
from uuid import UUID, uuid4
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from app.core.config import ROOT
from app.modules.identity.service import current_user
from app.modules.quests.router import back, same_origin
from app.modules.tasks.models import Task
from app.modules.activity import service

router = APIRouter()
templates = Jinja2Templates(directory=ROOT / 'app/templates')

def render(request, **context):
    from app.main import PAGES
    return templates.TemplateResponse(request=request, name='focus.html', context={'app_name': request.app.state.settings.app_name, 'pages':PAGES, 'page':'focus', 'current':PAGES['focus'], **context})

@router.get('/focus')
def focus(request: Request, task: str = '', saved: bool = False):
    with request.app.state.database.transaction() as db:
        user = current_user(db, request.cookies.get('camp_session'))
        if not user:
            return back('/account')
        session = service.active(db,user.id)
        tasks = list(db.scalars(select(Task).where(Task.user_id == user.id, Task.deleted_at.is_(None), Task.status != 'completed').order_by(Task.title)))
        return render(request, session=session, tasks=tasks, selected=task, saved=saved, request_id=uuid4(), seconds=service.duration(session,datetime.now(timezone.utc)) if session else 0)

def apply(request, action, form):
    try:
        with request.app.state.database.transaction() as db:
            user=current_user(db,request.cookies.get('camp_session'))
            if not user:
                return back('/account')
            if action == 'start':
                service.start(db,user.id,str(form.get('mode','')),str(form.get('minutes','')),UUID(str(form['task_id'])) if form.get('task_id') else None,UUID(str(form['request_id'])))
            else:
                correction = str(form.get('confirmed_seconds', '')).strip()
                if correction and action != 'finish':
                    raise ValueError('仅结束计时时可确认有效时长')
                service.transition(db,user.id,UUID(str(form['session_id'])),action,int(correction) if correction else None)
            return back('/focus?saved=true' if action == 'finish' else '/focus')
    except (ValueError, KeyError) as error:
        return templates.TemplateResponse(request=request,name='focus_error.html',status_code=400,context={'error':str(error),'app_name':request.app.state.settings.app_name,'pages':__import__('app.main',fromlist=['PAGES']).PAGES,'page':'focus','current':__import__('app.main',fromlist=['PAGES']).PAGES['focus']})

@router.post('/focus/{action}')
async def focus_post(request: Request, action: str):
    same_origin(request)
    form=await request.form()
    return await run_in_threadpool(apply,request,action,form)
