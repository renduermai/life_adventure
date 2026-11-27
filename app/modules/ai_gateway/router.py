"""Authenticated JSON endpoints; no AI settings page in V2 step 2."""
import json
import base64
import re
from urllib.parse import urlsplit
from uuid import UUID
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from app.modules.identity.service import current_user
from app.modules.quests.router import same_origin
from app.modules.ai_gateway import service
from app.modules.ai_gateway.models import AIConfig, AIModuleBinding, AICallLog
from app.modules.ai_gateway.schemas import CreateConfig, EditConfig, Version, TestConnection, Binding
from app.modules.ai_gateway.security import AIError

router=APIRouter(prefix='/api/ai')


def response(data,status=200):
    return JSONResponse(jsonable_encoder(data),status_code=status)


def user_id(request):
    database=request.app.state.database
    if database.sessions is None:
        raise AIError('database_unavailable','数据库尚未配置',503)
    with database.transaction() as db:
        user=current_user(db,request.cookies.get('camp_session'))
        if not user:
            raise AIError('unauthorized','请先登录',401)
        return user.id


async def body(request,schema,max_bytes=32768):
    same_origin(request)
    content=bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content)>max_bytes:
            raise AIError('body_too_large','请求体过大',413)
    try:
        return schema.model_validate(json.loads(content))
    except (ValueError,TypeError,ValidationError):
        raise AIError('invalid_input','输入字段无效，请检查格式和长度',422) from None


def error_response(request,error):
    return response({'error':str(error),'code':error.code,'request_id':request.state.request_id},error.status)


def supabase_display(settings):
    """Allowlist display values only; never serialize Settings or server credentials."""
    def secret(name):
        value=getattr(settings,name,None)
        return value.get_secret_value().strip() if value else ''
    server_keys=[secret('supabase_secret_key'),secret('supabase_service_role_key')]
    public_key=None;kind=None
    for name in ('supabase_publishable_key','supabase_anon_key'):
        value=secret(name)
        if not value or value in server_keys or len(value)>8192:continue
        valid=bool(re.fullmatch(r'sb_publishable_[A-Za-z0-9_-]+',value))
        if not valid and re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',value):
            try:
                segment=value.split('.')[1]
                payload=json.loads(base64.urlsafe_b64decode(segment+'='*(-len(segment)%4)))
                # A role check prevents accidental service_role exposure; this is not JWT authentication.
                valid=isinstance(payload,dict) and payload.get('role')=='anon'
            except (ValueError,TypeError,UnicodeError):pass
        if valid:public_key=value;kind='Publishable Key' if value.startswith('sb_publishable_') else 'anon Key';break
    raw_url=(settings.supabase_url or '').strip();project_url=None;dashboard='https://supabase.com/dashboard'
    try:
        parsed=urlsplit(raw_url)
        if (parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password
                and parsed.path in ('','/') and not parsed.query and not parsed.fragment and parsed.port in (None,443)):
            project_url='https://'+parsed.netloc.rstrip('/')
            match=re.fullmatch(r'([a-z]{20})\.supabase\.co',parsed.hostname)
            if match:dashboard+='/'+'project/'+match.group(1)
    except ValueError:pass
    server_configured=any(server_keys)
    bucket_configured=bool((settings.supabase_storage_bucket or '').strip())
    metadata={'name':'Supabase','service_type':'数据库 / 图片存储',
        'configured':bool(project_url and server_configured and bucket_configured),
        'project_url':project_url,'project_url_configured':bool(raw_url),'dashboard_url':dashboard,
        'public_key_configured':bool(public_key),'public_key_type':kind,
        'public_key_invalid':bool(not public_key and (secret('supabase_publishable_key') or secret('supabase_anon_key'))),
        'public_key_masked':'••••••••' if public_key else None,'server_key_configured':server_configured,
        'storage_bucket_configured':bucket_configured}
    return metadata,public_key


@router.get('/supabase')
def supabase_config(request:Request):
    try:
        user_id(request)
        metadata,_=supabase_display(request.app.state.settings)
        return JSONResponse(metadata,headers={'Cache-Control':'no-store','Vary':'Cookie'})
    except AIError as error:return error_response(request,error)


@router.post('/supabase/public-key/copy')
def supabase_public_key(request:Request):
    same_origin(request)
    try:
        user_id(request)
        _,key=supabase_display(request.app.state.settings)
        if not key:raise AIError('public_key_unavailable','未配置可公开使用的Publishable/anon Key',409)
        return JSONResponse({'public_key':key},headers={'Cache-Control':'no-store','Vary':'Cookie'})
    except AIError as error:return error_response(request,error)


@router.get('/configs')
def configs(request:Request):
    try:
        owner=user_id(request)
        with request.app.state.database.transaction() as db:
            return response([service.public(c) for c in db.scalars(select(AIConfig).where(AIConfig.user_id==owner,AIConfig.deleted_at.is_(None)).order_by(AIConfig.created_at))])
    except AIError as error:
        return error_response(request,error)


@router.get('/configs/{config_id}')
def config_detail(request:Request,config_id:UUID):
    try:
        owner=user_id(request)
        with request.app.state.database.transaction() as db:
            return response(service.public(service.get_config(db,owner,config_id)))
    except AIError as error:
        return error_response(request,error)


@router.post('/configs')
async def create(request:Request):
    try:
        owner=await run_in_threadpool(user_id,request)
        data=await body(request,CreateConfig)
        def apply():
            with request.app.state.database.transaction() as db:
                return service.public(service.create_config(db,owner,data,request.app.state.settings))
        return response(await run_in_threadpool(apply),201)
    except AIError as error:
        return error_response(request,error)


@router.patch('/configs/{config_id}')
async def edit(request:Request,config_id:UUID):
    try:
        owner=await run_in_threadpool(user_id,request)
        data=await body(request,EditConfig)
        def apply():
            with request.app.state.database.transaction() as db:
                return service.public(service.edit_config(db,owner,config_id,data,request.app.state.settings))
        return response(await run_in_threadpool(apply))
    except AIError as error:
        return error_response(request,error)


@router.delete('/configs/{config_id}')
async def remove(request:Request,config_id:UUID):
    try:
        owner=await run_in_threadpool(user_id,request)
        data=await body(request,Version)
        def apply():
            with request.app.state.database.transaction() as db:
                service.remove_config(db,owner,config_id,data.expected_version)
        await run_in_threadpool(apply)
        return response({'deleted':True})
    except AIError as error:
        return error_response(request,error)


@router.post('/configs/{config_id}/default')
async def default(request:Request,config_id:UUID):
    try:
        owner=await run_in_threadpool(user_id,request)
        data=await body(request,Version)
        def apply():
            with request.app.state.database.transaction() as db:
                return service.public(service.set_default(db,owner,config_id,data.expected_version))
        return response(await run_in_threadpool(apply))
    except AIError as error:
        return error_response(request,error)


@router.post('/configs/{config_id}/test')
async def test(request:Request,config_id:UUID):
    try:
        owner=await run_in_threadpool(user_id,request)
        data=await body(request,TestConnection)
        gateway=service.AIService(request.app.state.database,request.app.state.settings)
        result=await run_in_threadpool(gateway.generate,owner,'connection_test',
            [{'role':'user','content':'Reply with OK.'}],data.request_id,
            config_id=config_id,expected_version=data.expected_version)
        result.pop('content',None)
        return response(result|{'status':'succeeded'})
    except AIError as error:
        return error_response(request,error)


@router.put('/module-bindings/{module}')
async def binding(request:Request,module:str):
    try:
        owner=await run_in_threadpool(user_id,request)
        data=await body(request,Binding)
        def apply():
            with request.app.state.database.transaction() as db:
                service.bind(db,owner,module,data.config_id)
        await run_in_threadpool(apply)
        return response({'module':module,'config_id':data.config_id})
    except AIError as error:
        return error_response(request,error)


@router.get('/module-bindings')
def bindings(request:Request):
    try:
        owner=user_id(request)
        with request.app.state.database.transaction() as db:
            return response({r.module_key:r.config_id for r in db.scalars(select(AIModuleBinding).where(AIModuleBinding.user_id==owner))})
    except AIError as error:
        return error_response(request,error)


@router.get('/calls')
def calls(request:Request):
    try:
        owner=user_id(request)
        with request.app.state.database.transaction() as db:
            rows=db.scalars(select(AICallLog).where(AICallLog.user_id==owner).order_by(AICallLog.started_at.desc()).limit(100))
            return response([{key:getattr(r,key) for key in ('id','config_id','config_version','model_id','purpose','status','error_code','usage','elapsed_ms','started_at','finished_at')} for r in rows])
    except AIError as error:
        return error_response(request,error)
