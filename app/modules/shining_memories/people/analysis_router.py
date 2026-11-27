from uuid import UUID
from typing import Literal
from fastapi import APIRouter,Request,Query
from fastapi.encoders import jsonable_encoder
from starlette.concurrency import run_in_threadpool
from .router import execute,mutation
from ..router import owner,error_response
from ..shared.images import MediaError
from .analysis_schemas import Scope,Analyze
from . import analysis

router=APIRouter(prefix='/api/shining-memories')


@router.get('/people-sources')
def candidates(request:Request,kind:Literal['quest','task','note'],q:str=Query('',max_length=80),offset:int=Query(0,ge=0)):
    return execute(request,lambda db,uid:analysis.candidates(db,uid,kind,q,offset))


@router.post('/people/{pid}/preview')
async def preview(request:Request,pid:UUID):return await mutation(request,Scope,lambda db,uid,d:analysis.preview(db,uid,pid,d))


@router.get('/people/{pid}/analysis')
def view(request:Request,pid:UUID):return execute(request,lambda db,uid:analysis.view(db,uid,pid))


@router.post('/people/{pid}/analysis')
async def run(request:Request,pid:UUID):
    # Reuse bounded input/Origin validation, then run external I/O outside its transaction.
    captured={}
    result=await mutation(request,Analyze,lambda db,uid,d:captured.update(uid=uid,data=d) or {'accepted':True})
    if not captured:return result
    try:
        return jsonable_encoder(await run_in_threadpool(analysis.analyze,request.app.state.database,request.app.state.settings,captured['uid'],pid,captured['data']))
    except MediaError as error:return error_response(request,error)
