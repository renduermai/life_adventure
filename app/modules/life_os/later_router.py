"""Authenticated APIs for double-layer memories, actual mode, and scene templates."""
from uuid import UUID

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from app.modules.ai_gateway.router import body, user_id, response, error_response
from app.modules.ai_gateway.security import AIError
from app.modules.quests.router import same_origin
from . import later_service as service
from .later_schemas import ExperienceInput, ModeInput, SceneInput

router=APIRouter(prefix='/api/life-os')

@router.get('/schedule')
def schedule_read(request:Request):
    from .schedule import read
    try:return response(read(request.app.state.database,user_id(request)))
    except AIError as exc:return error_response(request,exc)

@router.post('/schedule/generate')
async def schedule_generate(request:Request):
    from .schedule import Generate, generate
    try:
        data=await body(request,Generate);uid=await run_in_threadpool(user_id,request)
        return response(await run_in_threadpool(generate,request.app.state.database,request.app.state.settings,uid,data.consent_external))
    except AIError as exc:return error_response(request,exc)

@router.get('/layers/experiences')
def list_experiences(request:Request,model:str,layer:str):
    try:return response(service.experience_list(request.app.state.database,user_id(request),model,layer))
    except AIError as exc:return error_response(request,exc)

@router.get('/layers/experiences/{eid}/history')
def experience_history(request:Request,eid:UUID):
    try:return response(service.experience_history(request.app.state.database,user_id(request),eid))
    except AIError as exc:return error_response(request,exc)

@router.post('/layers/experiences')
async def create_experience(request:Request):
    try:
        data=await body(request,ExperienceInput);uid=await run_in_threadpool(user_id,request)
        return response(await run_in_threadpool(service.save_experience,request.app.state.database,uid,data))
    except AIError as exc:return error_response(request,exc)

@router.put('/layers/experiences/{eid}')
async def update_experience(request:Request,eid:UUID):
    try:
        data=await body(request,ExperienceInput);uid=await run_in_threadpool(user_id,request)
        return response(await run_in_threadpool(service.save_experience,request.app.state.database,uid,data,eid))
    except AIError as exc:return error_response(request,exc)

@router.delete('/layers/experiences/{eid}')
def delete_experience(request:Request,eid:UUID):
    try:
        same_origin(request);uid=user_id(request)
        return response(service.delete_experience(request.app.state.database,uid,eid))
    except AIError as exc:return error_response(request,exc)

@router.get('/mode')
def mode(request:Request):
    try:return response(service.mode_read(request.app.state.database,user_id(request)))
    except AIError as exc:return error_response(request,exc)

@router.post('/mode')
async def choose_mode(request:Request):
    try:
        data=await body(request,ModeInput);uid=await run_in_threadpool(user_id,request)
        return response(await run_in_threadpool(service.mode_choose,request.app.state.database,uid,data.mode))
    except AIError as exc:return error_response(request,exc)

@router.post('/mode/follow-ai')
def follow_ai(request:Request):
    try:
        same_origin(request);uid=user_id(request)
        return response(service.mode_choose(request.app.state.database,uid,None,True))
    except AIError as exc:return error_response(request,exc)

@router.get('/scenes')
def scenes(request:Request):
    try:return response(service.scene_list(request.app.state.database,user_id(request)))
    except AIError as exc:return error_response(request,exc)

@router.get('/scenes/current')
def current_scene(request:Request):
    try:
        uid=user_id(request)
        from app.modules.identity.models import User
        with request.app.state.database.transaction() as db:
            timezone_name=db.get(User,uid).timezone
        return response(service.scene_current(request.app.state.database,uid,timezone_name))
    except AIError as exc:return error_response(request,exc)

@router.post('/scenes')
async def create_scene(request:Request):
    try:
        data=await body(request,SceneInput);uid=await run_in_threadpool(user_id,request)
        return response(await run_in_threadpool(service.save_scene,request.app.state.database,uid,data))
    except AIError as exc:return error_response(request,exc)

@router.put('/scenes/{scene_id}')
async def update_scene(request:Request,scene_id:UUID):
    try:
        data=await body(request,SceneInput);uid=await run_in_threadpool(user_id,request)
        return response(await run_in_threadpool(service.save_scene,request.app.state.database,uid,data,scene_id))
    except AIError as exc:return error_response(request,exc)

@router.post('/scenes/{scene_id}/copy')
async def copy_scene(request:Request,scene_id:UUID):
    try:
        data=await body(request,SceneInput);uid=await run_in_threadpool(user_id,request)
        return response(await run_in_threadpool(service.save_scene,request.app.state.database,uid,data,copy_id=scene_id))
    except AIError as exc:return error_response(request,exc)

@router.post('/scenes/{scene_id}/select')
def select_scene(request:Request,scene_id:UUID):
    try:
        same_origin(request);uid=user_id(request)
        return response(service.scene_select(request.app.state.database,uid,scene_id))
    except AIError as exc:return error_response(request,exc)

@router.get('/scenes/{scene_id}/history')
def scene_revisions(request:Request,scene_id:UUID):
    try:return response(service.scene_history(request.app.state.database,user_id(request),scene_id))
    except AIError as exc:return error_response(request,exc)

@router.delete('/scenes/{scene_id}')
def delete_scene(request:Request,scene_id:UUID):
    try:
        same_origin(request);uid=user_id(request)
        return response(service.delete_scene(request.app.state.database,uid,scene_id))
    except AIError as exc:return error_response(request,exc)

@router.get('/care')
def care_read(request:Request, day: str | None=None):
    from . import care
    from datetime import date
    try:
        selected=date.fromisoformat(day) if day else None
        return response(care.load(request.app.state.database,user_id(request),selected))
    except ValueError:return response({'error':'日期无效'},422)
    except AIError as exc:return error_response(request,exc)

@router.post('/care/{action}')
async def care_write(request:Request,action:str):
    from . import care
    operations={'save':(care.Edit,care.save),'check':(care.Check,care.check),'feedback':(care.Feedback,care.feedback)}
    try:
        if action not in operations:raise AIError('not_found','操作不存在',404)
        schema,fn=operations[action];data=await body(request,schema);uid=await run_in_threadpool(user_id,request)
        return response(await run_in_threadpool(fn,request.app.state.database,uid,data))
    except AIError as exc:return error_response(request,exc)

@router.post('/attractors/{action}')
async def attractors_api(request:Request,action:str):
    from . import attractors
    try:
        data=await body(request,attractors.RequestData,max_bytes=1048576);uid=await run_in_threadpool(user_id,request)
        if action=='read':return response(await run_in_threadpool(attractors.read,request.app.state.database,uid,data))
        if action=='analyze':return response(await run_in_threadpool(attractors.generate,request.app.state.database,request.app.state.settings,uid,data))
        raise AIError('not_found','操作不存在',404)
    except AIError as exc:return error_response(request,exc)

@router.post('/attractors/events/{eid}')
async def attractor_event(request:Request,eid:UUID):
    from . import attractors
    try:
        data=await body(request,attractors.RequestData,max_bytes=1048576);uid=await run_in_threadpool(user_id,request)
        return response(await run_in_threadpool(attractors.event_detail,request.app.state.database,uid,eid,data))
    except AIError as exc:return error_response(request,exc)
