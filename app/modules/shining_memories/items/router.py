from uuid import UUID
from fastapi import APIRouter,Request,Query
from ..people.router import execute,mutation
from ..people.schemas import Version
from . import service
from .schemas import Create,Edit
router=APIRouter(prefix='/api/shining-memories/items')

@router.get('')
def listing(request:Request,category:str=Query('',max_length=120),offset:int=Query(0,ge=0)):
    return execute(request,lambda db,uid:service.listing(db,uid,category,offset))
@router.post('')
async def create(request:Request):return await mutation(request,Create,service.create)
@router.get('/{iid}')
def detail(request:Request,iid:UUID):return execute(request,lambda db,uid:service.public(service.get(db,uid,iid),service.today(db,uid)))
@router.patch('/{iid}')
async def edit(request:Request,iid:UUID):return await mutation(request,Edit,lambda db,uid,d:service.mutate(db,uid,iid,d))
@router.delete('/{iid}')
async def delete(request:Request,iid:UUID):return await mutation(request,Version,lambda db,uid,d:service.mutate(db,uid,iid,d,True))
