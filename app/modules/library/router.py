import json
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from app.modules.identity.service import current_user
from app.modules.quests.router import same_origin
from app.modules.library import service
from app.modules.library.schemas import Create, Update, Delete

router=APIRouter(prefix='/api/library')


def execute(request, operation):
    try:
        database=request.app.state.database
        if database.sessions is None: raise HTTPException(503,'数据库尚未配置')
        with database.transaction() as db:
            user=current_user(db,request.cookies.get('camp_session'))
            if not user: raise HTTPException(401,'请先登录')
            return operation(db,user.id)
    except HTTPException as exc:
        return JSONResponse({'error':exc.detail,'request_id':request.state.request_id},status_code=exc.status_code)


async def mutation(request,schema,operation):
    try:
        same_origin(request)
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>32768: raise HTTPException(413,'请求体过大')
        try: data=schema.model_validate(json.loads(raw))
        except (ValueError,TypeError,ValidationError): raise HTTPException(422,'输入字段无效，请检查格式和长度') from None
        return await run_in_threadpool(execute,request,lambda db,uid:operation(db,uid,data))
    except HTTPException as exc:
        return JSONResponse({'error':exc.detail,'request_id':request.state.request_id},status_code=exc.status_code)


@router.get('/targets')
def targets(request:Request):
    return execute(request,service.targets)


@router.get('/links')
def listing(request:Request,offset:int=Query(default=0,ge=0),main_quest_id:UUID|None=None,task_id:UUID|None=None):
    return execute(request,lambda db,uid:service.listing(db,uid,offset,main_quest_id,task_id))


@router.get('/links/{link_id}')
def detail(request:Request,link_id:UUID):
    return execute(request,lambda db,uid:service.public(service.get(db,uid,link_id),service.targets(db,uid)))


@router.post('/links')
async def create(request:Request):
    return await mutation(request,Create,service.create)


@router.patch('/links/{link_id}')
async def update(request:Request,link_id:UUID):
    return await mutation(request,Update,lambda db,uid,data:service.mutate(db,uid,link_id,data))


@router.delete('/links/{link_id}')
async def delete(request:Request,link_id:UUID):
    return await mutation(request,Delete,lambda db,uid,data:service.mutate(db,uid,link_id,data,True))


@router.post('/links/{link_id}/copies')
async def copied(request:Request,link_id:UUID):
    from app.modules.library.schemas import Copy
    return await mutation(request,Copy,lambda db,uid,data:service.copied(db,uid,link_id,data))
