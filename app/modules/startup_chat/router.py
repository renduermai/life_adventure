from uuid import UUID
from fastapi import APIRouter, Query, Request
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from app.modules.ai_gateway.router import body, error_response, user_id
from app.modules.ai_gateway.security import AIError
from app.modules.startup_chat import service
from app.modules.startup_chat.models import Conversation, ChatTurn
from app.modules.startup_chat.schemas import MessageInput

router = APIRouter(prefix='/api/startup/chat')


@router.get('/conversations')
def conversations(request: Request, offset: int = Query(default=0, ge=0)):
    try:
        uid = user_id(request)
        with request.app.state.database.transaction() as db:
            rows = list(db.scalars(select(Conversation).where(Conversation.user_id == uid).order_by(Conversation.created_at.desc(), Conversation.id.desc()).offset(offset).limit(21)))
            return {'items': [{'id': r.id, 'title': r.title, 'version': r.version, 'created_at': r.created_at} for r in rows[:20]], 'next_offset': offset + 20 if len(rows) > 20 else None}
    except AIError as exc:
        return error_response(request, exc)


@router.get('/conversations/{cid}')
def history(request: Request, cid: UUID, before: int | None = Query(default=None, ge=1)):
    try:
        uid = user_id(request)
        with request.app.state.database.transaction() as db:
            chat = service.conversation(db, uid, cid)
            query = select(ChatTurn).where(ChatTurn.conversation_id == cid, ChatTurn.user_id == uid)
            if before is not None:
                query = query.where(ChatTurn.sequence < before)
            rows = list(db.scalars(query.order_by(ChatTurn.sequence.desc()).limit(21)))
            return {'id': cid, 'version': chat.version, 'items': [service.public(r) for r in reversed(rows[:20])], 'next_before': rows[19].sequence if len(rows) > 20 else None}
    except AIError as exc:
        return error_response(request, exc)


@router.post('/messages')
async def send(request: Request):
    try:
        data = await body(request, MessageInput)
        uid = await run_in_threadpool(user_id, request)
        return await run_in_threadpool(service.send, request.app.state.database, request.app.state.settings, uid, data)
    except AIError as exc:
        return error_response(request, exc)
