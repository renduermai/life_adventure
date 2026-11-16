from uuid import UUID
from fastapi import APIRouter, Query, Request
from starlette.concurrency import run_in_threadpool
from app.modules.ai_gateway.router import body, user_id, error_response
from app.modules.ai_gateway.security import AIError
from app.modules.distractions import service
from app.modules.distractions.schemas import Create, Delete

router = APIRouter(prefix='/api/distractions/notes')


@router.get('')
def listing(request: Request, offset: int = Query(default=0, ge=0)):
    try:
        uid = user_id(request)
        with request.app.state.database.transaction() as db:
            return service.listing(db, uid, offset)
    except AIError as exc:
        return error_response(request, exc)


@router.get('/{note_id}')
def read(request: Request, note_id: UUID):
    try:
        uid = user_id(request)
        with request.app.state.database.transaction() as db:
            return service.public(service.get(db, uid, note_id))
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


@router.delete('/{note_id}')
async def delete(request: Request, note_id: UUID):
    return await mutation(request, Delete, lambda db, uid, data: service.delete(db, uid, note_id, data))


@router.post('/classifications')
async def classify_notes(request: Request):
    from app.modules.distractions.classification_service import ClassifyInput, classify
    try:
        data = await body(request, ClassifyInput)
        uid = await run_in_threadpool(user_id, request)
        return await run_in_threadpool(classify, request.app.state.database, request.app.state.settings, uid, data.request_id)
    except AIError as exc:
        return error_response(request, exc)


@router.get('/classification/current')
def classification_current(request: Request):
    from app.modules.distractions.classification_service import view
    try:
        uid = user_id(request)
        with request.app.state.database.transaction() as db:
            return view(db, uid)
    except AIError as exc:
        return error_response(request, exc)
