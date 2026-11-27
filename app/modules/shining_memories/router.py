"""Shared authenticated, bounded image endpoints; business CRUD follows later."""
from uuid import UUID
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from app.modules.identity.service import current_user
from app.modules.quests.router import same_origin
from fastapi import HTTPException
from .shared.images import MAX_BYTES, MediaError, normalize_image
from .shared.storage import SupabaseStorage
from .shared import service

router = APIRouter(prefix='/api/shining-memories')


def owner(request):
    database = request.app.state.database
    if database.sessions is None:
        raise MediaError('database_unavailable', '数据库尚未配置', 503)
    with database.transaction() as db:
        user = current_user(db, request.cookies.get('camp_session'))
        if not user:
            raise MediaError('unauthorized', '请先登录', 401)
        return user.id


def storage(request, bucket=None):
    return SupabaseStorage(request.app.state.settings, bucket)


def error_response(request, error):
    return JSONResponse({'error': error.message, 'code': error.code,
        'request_id': request.state.request_id}, status_code=error.status)


@router.get('/status')
def status(request: Request):
    try:
        owner(request)
        try:
            store = storage(request)
        except MediaError as error:
            return {'storage_configured': False, 'storage_available': False, 'storage_checked': False,
                'storage_error_code': error.code, 'storage_message': error.message}
        try:
            store.ensure_private()
        except MediaError as error:
            return {'storage_configured': True, 'storage_available': False, 'storage_checked': True,
                'storage_error_code': error.code, 'storage_message': error.message}
        return {'storage_configured': True, 'storage_available': True, 'storage_checked': True,
            'backend': 'supabase', 'private': True}
    except MediaError as error:
        return error_response(request, error)


async def save(request, asset_id=None):
    try:
        try:
            same_origin(request)
        except HTTPException:
            raise MediaError('origin', '请从当前网站提交图片', 403) from None
        uid = await run_in_threadpool(owner, request)
        try:
            request_id = UUID(request.query_params['request_id'])
            expected = int(request.query_params['expected_version']) if asset_id else None
            if expected is not None and expected < 1:
                raise ValueError()
        except (KeyError, ValueError):
            raise MediaError('input', '上传编号或图片版本无效') from None
        store = storage(request)
        # The body is raw image bytes, not multipart: no parser spooling to local disk.
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > MAX_BYTES:
                raise MediaError('image_size', '图片不得超过5MB', 413)
            raw.extend(chunk)
        image = await run_in_threadpool(normalize_image, bytes(raw), request.query_params.get('filename', ''))
        return await run_in_threadpool(service.upload, request.app.state.database, store,
            uid, image, request_id, asset_id, expected)
    except MediaError as error:
        return error_response(request, error)


@router.post('/assets')
async def create(request: Request):
    return await save(request)


@router.put('/assets/{asset_id}')
async def replace(request: Request, asset_id: UUID):
    return await save(request, asset_id)


@router.get('/assets/{asset_id}/metadata')
def metadata(request: Request, asset_id: UUID):
    try:
        uid = owner(request)
        with request.app.state.database.transaction() as db:
            asset = service.get_asset(db, uid, asset_id)
            return service.public(asset, service.current_object(db, uid, asset_id))
    except MediaError as error:
        return error_response(request, error)


@router.get('/assets/{asset_id}')
def read(request: Request, asset_id: UUID):
    try:
        uid = owner(request)
        data, info = service.read(request.app.state.database,
            lambda bucket: storage(request, bucket), uid, asset_id)
        return Response(data, media_type=info['content_type'], headers={
            'Cache-Control': 'private, no-store', 'Content-Disposition': 'inline; filename="image.webp"'})
    except MediaError as error:
        return error_response(request, error)


@router.delete('/assets/{asset_id}')
async def delete(request: Request, asset_id: UUID):
    try:
        try:
            same_origin(request)
        except HTTPException:
            raise MediaError('origin', '请从当前网站删除图片', 403) from None
        uid = await run_in_threadpool(owner, request)
        try:
            expected = int(request.query_params['expected_version'])
            if expected < 1:
                raise ValueError()
        except (KeyError, ValueError):
            raise MediaError('input', '图片版本无效') from None
        return await run_in_threadpool(service.delete, request.app.state.database, uid, asset_id, expected)
    except MediaError as error:
        return error_response(request, error)
