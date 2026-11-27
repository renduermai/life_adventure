"""Authenticated endpoints for evidence browsing and AI probing."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from starlette.concurrency import run_in_threadpool

from app.modules.ai_gateway.router import body, error_response, response, user_id
from app.modules.ai_gateway.security import AIError
from app.modules.quests.router import same_origin

from . import service
from .schemas import CultivationEdit, DirectionEdit, EntryEdit, ObservationEdit, Resolve, Strict, Submit

router = APIRouter(prefix='/api/spirit-root')


def read(request, operation):
    try:
        uid = user_id(request)
        with request.app.state.database.transaction() as db:
            return response(operation(db, uid))
    except AIError as error:
        return error_response(request, error)


@router.get('')
def overview(request: Request):
    return read(request, service.overview)


@router.get('/entries/{entry_id}')
def history(request: Request, entry_id: UUID, offset: int = Query(0, ge=0)):
    return read(request, lambda db, uid: service.history(db, uid, entry_id, offset))


@router.get('/sources')
def sources(request: Request, offset: int = Query(0, ge=0)):
    return read(request, lambda db, uid: service.list_sources(db, uid, offset))


@router.delete('/sources/{source_id}')
def delete_source(request: Request, source_id: UUID):
    same_origin(request)
    return read(request, lambda db, uid: service.remove_source(db, uid, source_id))


@router.get('/sources/{source_id}')
def original(request: Request, source_id: UUID):
    def fetch(db, uid):
        row = service.get_source(db, uid, source_id)
        return service.source_view(row) | {'original': row.original}
    return read(request, fetch)


@router.post('/probe')
async def probe(request: Request):
    try:
        data = await body(request, Submit, max_bytes=65536)
        uid = await run_in_threadpool(user_id, request)
        result = await run_in_threadpool(
            service.probe, request.app.state.database, request.app.state.settings, uid, data.original,
        )
        return response(result)
    except AIError as error:
        return error_response(request, error)


@router.post('/review/{observation_id}')
async def resolve(request: Request, observation_id: UUID):
    try:
        data = await body(request, Resolve)
        return await run_in_threadpool(read, request, lambda db, uid: service.resolve(
            db, uid, observation_id, data.choice,
        ))
    except AIError as error:
        return error_response(request, error)

class Enrich(Strict):
    pass


@router.post('/sources/{source_id}/enrich')
async def enrich(request: Request, source_id: UUID):
    try:
        await body(request, Enrich)
        uid = await run_in_threadpool(user_id, request)
        return response(await run_in_threadpool(
            service.enrich, request.app.state.database, request.app.state.settings, uid, source_id,
        ))
    except AIError as error:
        return error_response(request, error)

async def patch_record(request, schema, operation, max_bytes=32768):
    try:
        data = await body(request, schema, max_bytes=max_bytes)
        return await run_in_threadpool(read, request, lambda db, uid: operation(db, uid, data))
    except AIError as error:
        return error_response(request, error)


@router.patch('/sources/{source_id}')
async def update_source(request: Request, source_id: UUID):
    return await patch_record(request, Submit, lambda db, uid, data: service.edit_source(
        db, uid, source_id, data,
    ), max_bytes=65536)


@router.patch('/entries/{entry_id}')
async def update_entry(request: Request, entry_id: UUID):
    return await patch_record(request, EntryEdit, lambda db, uid, data: service.manage_entry(db, uid, entry_id, data))


@router.delete('/entries/{entry_id}')
def delete_entry(request: Request, entry_id: UUID):
    same_origin(request)
    return read(request, lambda db, uid: service.manage_entry(db, uid, entry_id))


@router.patch('/observations/{observation_id}')
async def update_observation(request: Request, observation_id: UUID):
    return await patch_record(request, ObservationEdit, lambda db, uid, data: service.manage_observation(
        db, uid, observation_id, data,
    ))


@router.delete('/observations/{observation_id}')
def delete_observation(request: Request, observation_id: UUID):
    same_origin(request)
    return read(request, lambda db, uid: service.manage_observation(db, uid, observation_id))


Group = Literal['cultivation', 'directions', 'totem']


@router.patch('/development/{group}/{key}')
async def update_development(request: Request, group: Group, key: str, source_id: UUID):
    schema = DirectionEdit if group == 'directions' else CultivationEdit
    return await patch_record(request, schema, lambda db, uid, data: service.manage_development(
        db, uid, group, key, source_id, data,
    ))


@router.delete('/development/{group}/{key}')
def delete_development(request: Request, group: Group, key: str, source_id: UUID | None = None):
    same_origin(request)
    return read(request, lambda db, uid: service.manage_development(db, uid, group, key, source_id))
