"""Read-only page shell for the life operating system."""
import logging
from uuid import UUID
from fastapi import Query
from starlette.concurrency import run_in_threadpool
from app.modules.ai_gateway.router import body, user_id, response, error_response
from app.modules.ai_gateway.security import AIError
from . import service
from .schemas import Send, Analyze, Correct, EditMessage
from app.modules.quests.router import same_origin

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config import ROOT

logger = logging.getLogger("adventure_camp.life_os")
router = APIRouter()
templates = Jinja2Templates(directory=ROOT / "app/templates")


@router.get("/life-os", response_class=HTMLResponse)
def life_os_page(request: Request):
    database = request.app.state.database
    settings = request.app.state.settings
    timezone_name = settings.app_timezone
    if database.sessions is not None:
        try:
            from app.modules.identity.service import current_user

            with database.transaction() as db:
                user = current_user(db, request.cookies.get("camp_session"))
                if user:
                    timezone_name = user.timezone
        except Exception as error:
            logger.warning("life_os_timezone_lookup_failed type=%s", type(error).__name__)

    return templates.TemplateResponse(request=request, name="life_os/page.html", context={
        "pages": request.app.state.pages,
        "page": "life-os",
        "current": request.app.state.pages["life-os"],
        "app_name": settings.app_name,
        "timezone_name": timezone_name,
    })


@router.get('/api/life-os/messages')
def messages(request: Request, offset: int = Query(default=0,ge=0,le=100000), limit:int=Query(default=20,ge=1,le=50)):
    try: return response(service.history(request.app.state.database,user_id(request),offset,limit))
    except AIError as exc: return error_response(request,exc)

@router.post('/api/life-os/messages')
async def send(request: Request):
    try:
        data=await body(request,Send,max_bytes=1048576)
        uid=await run_in_threadpool(user_id,request)
        return response(await run_in_threadpool(service.save,request.app.state.database,uid,data))
    except AIError as exc: return error_response(request,exc)

@router.post('/api/life-os/messages/{mid}/analyze')
async def analyze(request: Request, mid: UUID):
    try:
        data=await body(request,Analyze,max_bytes=1048576)
        uid=await run_in_threadpool(user_id,request)
        return response(await run_in_threadpool(service.analyze,request.app.state.database,request.app.state.settings,uid,mid,data))
    except AIError as exc: return error_response(request,exc)

@router.post('/api/life-os/analyses/{aid}/state')
async def correct(request: Request, aid: UUID):
    try:
        data=await body(request,Correct)
        uid=await run_in_threadpool(user_id,request)
        return response(await run_in_threadpool(service.correct,request.app.state.database,uid,aid,data))
    except AIError as exc: return error_response(request,exc)


@router.get('/api/life-os/messages/{mid}/analyses')
def versions(request: Request, mid: UUID, offset: int = Query(default=0,ge=0,le=100000)):
    try: return response(service.versions(request.app.state.database,user_id(request),mid,offset))
    except AIError as exc: return error_response(request,exc)

@router.get('/api/life-os/layer-points')
def layer_points(request:Request,rounds:int=Query(default=30)):
    from sqlalchemy import select
    from .models import Message,Analysis
    try:
        if rounds not in (1,5,15,30):raise AIError('invalid_input','展示轮数必须为1、5、15或30',422)
        uid=user_id(request)
        with request.app.state.database.transaction() as db:
            recent=select(Message.id).where(Message.user_id==uid).order_by(Message.created_at.desc(),Message.id.desc()).limit(rounds)
            latest=select(Analysis.id).where(Analysis.message_id==Message.id,Analysis.user_id==uid,Analysis.status=='succeeded').order_by(Analysis.created_at.desc(),Analysis.id.desc()).limit(1).correlate(Message).scalar_subquery()
            pairs=db.execute(select(Message,Analysis).join(Analysis,Analysis.id==latest).where(Message.user_id==uid,Message.id.in_(recent)).order_by(Message.created_at.desc(),Message.id.desc())).all()
            items=[{'message_id':str(message.id),'created_at':message.created_at,'text':message.content[:180],'life_layers':analysis.result.get('life_layers',[]),'need_layers':analysis.result.get('need_layers',[]),'reply':analysis.result.get('core_conflict','')} for message,analysis in pairs]
            return response({'items':items,'rounds':rounds})
    except AIError as exc:return error_response(request,exc)


@router.patch('/api/life-os/messages/{mid}')
async def edit_message(request: Request, mid: UUID):
    try:
        data = await body(request, EditMessage, max_bytes=1048576)
        uid = await run_in_threadpool(user_id, request)
        return response(await run_in_threadpool(service.change_message, request.app.state.database, uid, mid, data))
    except AIError as exc:
        return error_response(request, exc)


@router.delete('/api/life-os/messages/{mid}')
def delete_message(request: Request, mid: UUID):
    same_origin(request)
    try:
        return response(service.change_message(request.app.state.database, user_id(request), mid))
    except AIError as exc:
        return error_response(request, exc)
