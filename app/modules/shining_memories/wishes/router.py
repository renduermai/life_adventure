from uuid import UUID
from fastapi import APIRouter,Request,Query
from fastapi.encoders import jsonable_encoder
from starlette.concurrency import run_in_threadpool
from ..people.router import execute,mutation
from ..people.schemas import Version
from ..router import error_response
from ..shared.images import MediaError
from . import service,classification
from .schemas import Create,Edit,Price,Correct,Classify
router=APIRouter(prefix='/api/shining-memories/wishes')
@router.get('')
def listing(request:Request,category:str=Query('',max_length=120),offset:int=Query(0,ge=0)):
    return execute(request,lambda db,uid:service.listing(db,uid,category,offset))
@router.post('')
async def create(request:Request):return await mutation(request,Create,service.create)
@router.get('/{wid}')
def detail(request:Request,wid:UUID):return execute(request,lambda db,uid:service.public(db,service.get(db,uid,wid)))
@router.patch('/{wid}')
async def edit(request:Request,wid:UUID):return await mutation(request,Edit,lambda db,uid,d:service.mutate(db,uid,wid,d))
@router.delete('/{wid}')
async def delete(request:Request,wid:UUID):return await mutation(request,Version,lambda db,uid,d:service.mutate(db,uid,wid,d,True))
@router.get('/{wid}/prices')
def history(request:Request,wid:UUID,offset:int=Query(0,ge=0)):return execute(request,lambda db,uid:service.history(db,uid,wid,offset))
@router.post('/{wid}/prices')
async def price(request:Request,wid:UUID):return await mutation(request,Price,lambda db,uid,d:service.price(db,uid,wid,d))
@router.post('/{wid}/initial-price-correction')
async def correct(request:Request,wid:UUID):return await mutation(request,Correct,lambda db,uid,d:service.price(db,uid,wid,d,True))
@router.post('/{wid}/classify')
async def classify(request:Request,wid:UUID):
    captured={}
    result=await mutation(request,Classify,lambda db,uid,d:captured.update(uid=uid,data=d) or {'accepted':True})
    if not captured:return result
    try:return jsonable_encoder(await run_in_threadpool(classification.classify,request.app.state.database,request.app.state.settings,captured['uid'],wid,captured['data']))
    except MediaError as error:return error_response(request,error)
