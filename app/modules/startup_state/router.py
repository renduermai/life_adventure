import hashlib, json
from uuid import UUID
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from app.modules.identity.service import current_user, lock_user
from app.modules.quests.router import same_origin
from app.modules.startup_state.models import StateSnapshot, StateCurrent
from app.modules.ai_gateway.router import body, error_response
from app.modules.ai_gateway.security import AIError
from app.modules.startup_chat.service import validate_suggestion

router = APIRouter(prefix="/api/startup")
class StateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pressure: StrictInt = Field(ge=0, le=100)
    energy: StrictInt = Field(ge=0, le=100)
    difficulty: str = Field(default="", max_length=2000)
    confirmed: StrictBool
    request_id: UUID
    expected_generation: StrictInt = Field(ge=0)
    source_turn_id: UUID | None = None
    source_plan_id: UUID | None = None

def locate(p, e):
    return ("投入区" if p < 50 else "降噪区") if e >= 50 else ("激活区" if p < 50 else "修复区")

def owner(db, request):
    user = current_user(db, request.cookies.get("camp_session"))
    return user.id if user else None

def result(snapshot, generation):
    return {"snapshot_id":str(snapshot.id), "source_plan_id":str(snapshot.source_plan_id) if snapshot.source_plan_id else None, "source_turn_id":str(snapshot.source_turn_id) if snapshot.source_turn_id else None, "pressure":snapshot.pressure, "energy":snapshot.energy, "difficulty":snapshot.difficulty, "quadrant":locate(snapshot.pressure,snapshot.energy), "generation":generation, "created_at":snapshot.created_at.isoformat()}

@router.get('/history')
def history(request: Request, offset: int = Query(default=0, ge=0)):
    if request.app.state.database.sessions is None: return JSONResponse({'error':'数据库尚未配置'},503)
    with request.app.state.database.transaction() as db:
        uid=owner(db,request)
        if not uid: return JSONResponse({'error':'请先登录'},401)
        rows=list(db.scalars(select(StateSnapshot).where(StateSnapshot.user_id==uid).order_by(StateSnapshot.created_at.desc(),StateSnapshot.id.desc()).offset(offset).limit(21)))
        return {'items':[result(row,None) for row in rows[:20]], 'next_offset':offset+20 if len(rows)>20 else None}

@router.get("/current")
def read(request: Request):
    if request.app.state.database.sessions is None: return JSONResponse({"error":"数据库尚未配置"},503)
    with request.app.state.database.transaction() as db:
        user_id=owner(db,request)
        if not user_id: return JSONResponse({"error":"请先登录"},401)
        current=db.get(StateCurrent,user_id)
        return result(db.get(StateSnapshot,current.snapshot_id),current.generation) if current else {"generation":0, "state":None}

@router.post("/states")
async def save(request: Request):
    same_origin(request)
    try:
        data=await body(request,StateInput)
        if not data.confirmed or (data.source_turn_id and data.source_plan_id): raise ValueError()
    except AIError as exc: return error_response(request,exc)
    except (ValidationError,ValueError): return JSONResponse({"error":"请确认有效的压力和能量数值"},422)
    def execute():
        with request.app.state.database.transaction() as db:
            user_id=owner(db,request)
            if not user_id: return JSONResponse({"error":"请先登录"},401)
            lock_user(db,user_id)
            values=[data.pressure,data.energy,data.difficulty,data.expected_generation]
            if data.source_turn_id: values.append(str(data.source_turn_id))
            if data.source_plan_id: values.append("plan:"+str(data.source_plan_id))
            fingerprint=hashlib.sha256(json.dumps(values,ensure_ascii=False).encode()).hexdigest()
            old=db.scalar(select(StateSnapshot).where(StateSnapshot.user_id==user_id,StateSnapshot.request_id==data.request_id))
            current=db.get(StateCurrent,user_id)
            if old:
                if old.fingerprint!=fingerprint: return JSONResponse({"error":"提交编号已使用"},409)
                if not current or current.snapshot_id != old.id: return JSONResponse({"error":"状态已更新，请刷新后重试"},409)
                return result(old,current.generation if current else 0)
            generation=current.generation if current else 0
            if generation!=data.expected_generation: return JSONResponse({"error":"状态已在其他页面更新，请刷新后重试"},409)
            if data.source_turn_id: validate_suggestion(db,user_id,data.source_turn_id,generation)
            if data.source_plan_id:
                from app.modules.startup_chat.breakdown_service import get_plan, context, target, fresh
                plan=get_plan(db,user_id,data.source_plan_id)
                ctx,fp=context(db,user_id,*target(plan))
                if plan.status!='draft' or not fresh(plan,ctx,fp) or not (plan.advice or {}).get('state_advice',{}):
                    raise AIError('stale_suggestion','拆解状态建议已失效，请重新拆解或手动确认',409)
                if not plan.advice['state_advice']['ready']:raise AIError('invalid_suggestion','状态信息不足，请先继续对话',409)
            snapshot=StateSnapshot(user_id=user_id,request_id=data.request_id,fingerprint=fingerprint,pressure=data.pressure,energy=data.energy,difficulty=data.difficulty.strip(),source_turn_id=data.source_turn_id,source_plan_id=data.source_plan_id)
            db.add(snapshot); db.flush()
            if current: current.snapshot_id=snapshot.id; current.generation+=1
            else: current=StateCurrent(user_id=user_id,snapshot_id=snapshot.id,generation=1); db.add(current)
            db.flush()
            return result(snapshot,current.generation)
    if request.app.state.database.sessions is None: return JSONResponse({"error":"数据库尚未配置"},503)
    try: return await run_in_threadpool(execute)
    except AIError as exc: return error_response(request,exc)
