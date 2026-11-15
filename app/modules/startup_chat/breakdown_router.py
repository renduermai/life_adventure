from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Query, Request
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from app.modules.ai_gateway.router import user_id, body, error_response
from app.modules.ai_gateway.security import AIError
from app.modules.tasks.service import TaskError
from app.modules.startup_chat import breakdown_service as service
from app.modules.startup_chat.breakdown_models import BreakdownPlan
from app.modules.startup_chat.breakdown_schemas import Generate, Edit, Confirm, Check, Start

router=APIRouter(prefix='/api/startup/breakdowns')


@router.get('')
def history(request:Request,task_type:Literal['quest','task'],task_id:UUID,offset:int=Query(default=0,ge=0)):
    try:
        uid=user_id(request)
        with request.app.state.database.transaction() as db:
            ctx,_=service.context(db,uid,task_type,task_id)
            rows=list(db.scalars(service.query_target(uid,task_type,task_id).order_by(BreakdownPlan.created_at.desc(),BreakdownPlan.id.desc()).offset(offset).limit(21)))
            return {'target':ctx,'items':[service.public(db,uid,p) for p in rows[:20]],'next_offset':offset+20 if len(rows)>20 else None}
    except AIError as exc:return error_response(request,exc)


@router.get('/{pid}')
def read(request:Request,pid:UUID):
    try:
        uid=user_id(request)
        with request.app.state.database.transaction() as db:return service.public(db,uid,service.get_plan(db,uid,pid))
    except AIError as exc:return error_response(request,exc)


@router.post('')
async def generate(request:Request):
    try:
        data=await body(request,Generate);uid=await run_in_threadpool(user_id,request)
        return await run_in_threadpool(service.generate,request.app.state.database,request.app.state.settings,uid,data)
    except AIError as exc:return error_response(request,exc)


async def mutation(request,pid,schema,operation):
    try:
        data=await body(request,schema);uid=await run_in_threadpool(user_id,request)
        def apply():
            with request.app.state.database.transaction() as db:return operation(db,uid,pid,data)
        return await run_in_threadpool(apply)
    except AIError as exc:return error_response(request,exc)
    except TaskError as exc:return error_response(request,AIError('task_error',str(exc),exc.status_code))
    except ValueError as exc:return error_response(request,AIError('invalid_input',str(exc),422))


@router.patch('/{pid}')
async def edit(request:Request,pid:UUID):return await mutation(request,pid,Edit,service.edit)


@router.post('/{pid}/confirm')
async def confirm(request:Request,pid:UUID):return await mutation(request,pid,Confirm,service.confirm)


@router.patch('/{pid}/checklist')
async def check(request:Request,pid:UUID):return await mutation(request,pid,Check,service.check)


@router.post('/{pid}/start')
async def start(request:Request,pid:UUID):return await mutation(request,pid,Start,service.prepare_start)
