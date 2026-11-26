"""Read-only page shell for the life operating system."""
import logging
from uuid import UUID
from fastapi import Query
from starlette.concurrency import run_in_threadpool
from app.modules.ai_gateway.router import body, user_id, response, error_response
from app.modules.ai_gateway.security import AIError
from . import service
from .schemas import Send, Analyze, Correct

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
def messages(request: Request, offset: int = Query(default=0,ge=0,le=100000)):
    try: return response(service.history(request.app.state.database,user_id(request),offset))
    except AIError as exc: return error_response(request,exc)

@router.post('/api/life-os/messages')
async def send(request: Request):
    try:
        data=await body(request,Send)
        uid=await run_in_threadpool(user_id,request)
        return response(await run_in_threadpool(service.save,request.app.state.database,uid,data))
    except AIError as exc: return error_response(request,exc)

@router.post('/api/life-os/messages/{mid}/analyze')
async def analyze(request: Request, mid: UUID):
    try:
        data=await body(request,Analyze)
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
