from uuid import UUID
from fastapi import APIRouter,Request,Query
from starlette.concurrency import run_in_threadpool
from app.modules.ai_gateway.router import body,user_id,response,error_response
from app.modules.ai_gateway.security import AIError
from . import problems
from .problem_schemas import EditProblem,Version,Merge,EditEvent,MoveSource,Feedback,ImportNote
router=APIRouter(prefix='/api/life-os')

@router.get('/problems')
def listing(request:Request,offset:int=Query(0,ge=0,le=100000)):
    try:
        uid=user_id(request)
        with request.app.state.database.transaction() as db:return response(problems.listing(db,uid,offset))
    except AIError as exc:return error_response(request,exc)

@router.get('/problems/{pid}')
def detail(request:Request,pid:UUID,offset:int=Query(0,ge=0,le=100000)):
    try:
        uid=user_id(request)
        with request.app.state.database.transaction() as db:return response(problems.detail(db,uid,pid,offset))
    except AIError as exc:return error_response(request,exc)

@router.get('/events')
def events(request:Request,offset:int=Query(0,ge=0,le=100000)):
    from sqlalchemy import select
    from .problem_models import LifeEvent
    try:
        uid=user_id(request)
        with request.app.state.database.transaction() as db:
            rows=list(db.scalars(select(LifeEvent).where(LifeEvent.user_id==uid,LifeEvent.deleted_at.is_(None),problems.valid_event()).order_by(LifeEvent.occurred_at.desc(),LifeEvent.id.desc()).offset(offset).limit(21)))
            return response({'items':[problems.event_detail(db,uid,e) for e in rows[:20]],'next_offset':offset+20 if len(rows)>20 else None})
    except AIError as exc:return error_response(request,exc)

@router.get('/notes')
def notes(request:Request,offset:int=Query(0,ge=0,le=100000),q:str=Query('',max_length=100)):
    try:
        uid=user_id(request)
        with request.app.state.database.transaction() as db:return response(problems.notes(db,uid,offset,q))
    except AIError as exc:return error_response(request,exc)

async def mutation(request,schema,action,target):
    try:
        data=await body(request,schema);uid=await run_in_threadpool(user_id,request)
        return response(await run_in_threadpool(problems.mutate,request.app.state.database,uid,action,target,data))
    except AIError as exc:return error_response(request,exc)

@router.post('/problems/{pid}/edit')
async def edit(request:Request,pid:UUID):return await mutation(request,EditProblem,'edit_problem',pid)
@router.post('/problems/{pid}/delete')
async def delete(request:Request,pid:UUID):return await mutation(request,Version,'delete_problem',pid)
@router.post('/problems/{pid}/merge')
async def merge(request:Request,pid:UUID):return await mutation(request,Merge,'merge',pid)
@router.post('/events/{eid}/edit')
async def edit_event(request:Request,eid:UUID):return await mutation(request,EditEvent,'edit_event',eid)
@router.post('/events/{eid}/feedback')
async def feedback(request:Request,eid:UUID):return await mutation(request,Feedback,'feedback',eid)
@router.post('/sources/move')
async def move(request:Request):return await mutation(request,MoveSource,'move_source',UUID(int=0))
@router.post('/notes/import')
async def import_note(request:Request):return await mutation(request,ImportNote,'import_note',UUID(int=0))
