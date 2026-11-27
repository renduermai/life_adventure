import json
from uuid import UUID
from fastapi import APIRouter,Request,Query,HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from ..router import owner,error_response
from ..shared.images import MediaError
from app.modules.quests.router import same_origin
from . import service
from .schemas import PersonCreate,PersonEdit,FriendCreate,FriendEdit,Version,EventCreate,EventEdit



def execute(request,operation):
    try:
        uid=owner(request)
        with request.app.state.database.transaction() as db:return jsonable_encoder(operation(db,uid))
    except MediaError as error:return error_response(request,error)


async def mutation(request,schema,operation):
    try:
        try:same_origin(request)
        except HTTPException:raise MediaError('origin','请从当前网站操作',403) from None
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>65536:raise MediaError('body_size','请求内容过大',413)
        try:data=schema.model_validate(json.loads(raw))
        except (ValueError,TypeError,ValidationError):raise MediaError('input','输入字段无效，请检查格式及长度') from None
        return await run_in_threadpool(execute,request,lambda db,uid:operation(db,uid,data))
    except MediaError as error:return error_response(request,error)


def build_router(section, kind, create_schema, edit_schema):
    router = APIRouter(prefix=f'/api/shining-memories/{section}')

    @router.get('')
    def listing(request:Request,offset:int=Query(0,ge=0)):
        return execute(request,lambda db,uid:service.listing(db,uid,offset,kind))


    @router.post('')
    async def create(request:Request):return await mutation(request,create_schema,lambda db,uid,d:service.create(db,uid,d,kind))


    @router.get('/{pid}')
    def detail(request:Request,pid:UUID):return execute(request,lambda db,uid:service.public(db,service.get(db,uid,pid,kind),service.today(db,uid)))


    @router.patch('/{pid}')
    async def update(request:Request,pid:UUID):return await mutation(request,edit_schema,lambda db,uid,d:service.mutate(db,uid,pid,d,kind=kind))


    @router.delete('/{pid}')
    async def delete(request:Request,pid:UUID):return await mutation(request,Version,lambda db,uid,d:service.mutate(db,uid,pid,d,True,kind))


    @router.get('/{pid}/events')
    def events(request:Request,pid:UUID,offset:int=Query(0,ge=0)):return execute(request,lambda db,uid:service.events(db,uid,pid,offset,kind))


    @router.post('/{pid}/events')
    async def add_event(request:Request,pid:UUID):return await mutation(request,EventCreate,lambda db,uid,d:service.save_event(db,uid,pid,d,kind=kind))


    @router.patch('/{pid}/events/{eid}')
    async def edit_event(request:Request,pid:UUID,eid:UUID):return await mutation(request,EventEdit,lambda db,uid,d:service.save_event(db,uid,pid,d,eid,kind=kind))


    @router.delete('/{pid}/events/{eid}')
    async def delete_event(request:Request,pid:UUID,eid:UUID):return await mutation(request,Version,lambda db,uid,d:service.save_event(db,uid,pid,d,eid,True,kind))


    return router


router = build_router('people', 'mentor', PersonCreate, PersonEdit)
friends_router = build_router('friends', 'friend', FriendCreate, FriendEdit)
