"""Owner-scoped manual labels, independent of completion and AI recommendations."""
from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, StrictInt, Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from app.modules.ai_gateway.router import body, user_id, error_response
from app.modules.ai_gateway.security import AIError
from app.modules.identity.service import lock_user
from app.modules.quests.models import MainQuest
from app.modules.tasks.models import Task

FocusStatus = Literal['recommended', 'normal', 'not_recommended', 'deferred', 'routine_practice']
class Change(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: FocusStatus
    expected_version: StrictInt = Field(ge=1)

router = APIRouter()

def update(db, uid, model, target_id, data):
    lock_user(db, uid)
    item = db.scalar(select(model).where(model.id == target_id, model.user_id == uid, model.deleted_at.is_(None)))
    if not item:
        raise AIError('not_found', '任务不存在或不可修改', 404)
    if item.manual_focus_version != data.expected_version:
        raise AIError('version_conflict', '标记已在其他页面改变，请刷新后再选择', 409)
    item.manual_focus_status = data.status
    item.manual_focus_version += 1
    return {'status': item.manual_focus_status, 'version': item.manual_focus_version}

async def change(request, model, target_id):
    try:
        data = await body(request, Change)
        uid = await run_in_threadpool(user_id, request)
        def save():
            with request.app.state.database.transaction() as db:
                return update(db, uid, model, target_id, data)
        return await run_in_threadpool(save)
    except AIError as exc:
        return error_response(request, exc)

@router.patch('/api/quests/{target_id}/manual-focus')
async def quest(request: Request, target_id: UUID):
    return await change(request, MainQuest, target_id)

@router.patch('/api/tasks/{target_id}/manual-focus')
async def task(request: Request, target_id: UUID):
    return await change(request, Task, target_id)
