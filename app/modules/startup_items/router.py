from uuid import UUID
from fastapi import APIRouter, Query, Request
from starlette.concurrency import run_in_threadpool
from app.modules.ai_gateway.router import body, user_id, error_response
from app.modules.ai_gateway.security import AIError
from app.modules.startup_items import service
from app.modules.startup_items.schemas import Create, Edit, Delete
from app.modules.startup_items.analysis import AnalyzeInput, analyze

router = APIRouter(prefix='/api/startup/items')


@router.get('')
def listing(request: Request, offset: int = Query(default=0, ge=0)):
    try:
        uid = user_id(request)
        with request.app.state.database.transaction() as db:
            return service.listing(db, uid, offset)
    except AIError as exc:
        return error_response(request, exc)


@router.get('/{item_id}')
def read(request: Request, item_id: UUID):
    try:
        uid = user_id(request)
        with request.app.state.database.transaction() as db:
            return service.public(service.get(db, uid, item_id))
    except AIError as exc:
        return error_response(request, exc)


async def mutation(request, schema, operation):
    try:
        data = await body(request, schema)
        uid = await run_in_threadpool(user_id, request)
        def execute():
            with request.app.state.database.transaction() as db:
                return operation(db, uid, data)
        return await run_in_threadpool(execute)
    except AIError as exc:
        return error_response(request, exc)


@router.post('')
async def create(request: Request):
    return await mutation(request, Create, service.create)


@router.patch('/{item_id}')
async def edit(request: Request, item_id: UUID):
    return await mutation(request, Edit, lambda db, uid, data: service.mutate(db, uid, item_id, data))


@router.delete('/{item_id}')
async def delete(request: Request, item_id: UUID):
    return await mutation(request, Delete, lambda db, uid, data: service.mutate(db, uid, item_id, data, delete=True))


@router.post('/{item_id}/analyze')
async def analyze_item(request: Request, item_id: UUID):
    try:
        data = await body(request, AnalyzeInput)
        uid = await run_in_threadpool(user_id, request)
        return await run_in_threadpool(analyze, request.app.state.database, request.app.state.settings,
                                      uid, item_id, data.request_id)
    except AIError as exc:
        return error_response(request, exc)
