from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from app.modules.ai_gateway.router import body, user_id, error_response
from app.modules.ai_gateway.security import AIError
from app.modules.startup_chat import session_service
from app.modules.startup_chat.session_schemas import Message

router = APIRouter(prefix='/api/startup/chat')


@router.get('/context')
def context(request: Request, task_type: Literal['quest','task'] | None = None, task_id: UUID | None = None):
    try:
        uid = user_id(request)
        with request.app.state.database.transaction() as db:
            return session_service.context(db, uid, task_type, task_id)
    except AIError as exc:
        return error_response(request, exc)


@router.post('/messages')
async def send(request: Request):
    try:
        data = await body(request, Message)
        uid = await run_in_threadpool(user_id, request)
        return await run_in_threadpool(session_service.send, request.app.state.database, request.app.state.settings, uid, data)
    except AIError as exc:
        return error_response(request, exc)
