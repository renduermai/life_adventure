from uuid import UUID
from typing import Literal
from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,Field,ValidationError
from starlette.concurrency import run_in_threadpool
from app.modules.quests.router import same_origin
from app.modules.ai_gateway.router import user_id,error_response
from app.modules.ai_gateway.security import AIError
from app.modules.identity.service import lock_user
from app.modules.task_recommendation import service
from app.modules.task_recommendation.models import TaskAnalysis

router=APIRouter(prefix='/api/startup')

@router.get('/target')
def target(request:Request,task_type:Literal['quest','task'],task_id:UUID):
 from app.modules.startup_state.context import target_context
 from app.modules.startup_state.models import StateCurrent,StateSnapshot
 try:
  uid=user_id(request)
  with request.app.state.database.transaction() as db:
   context=target_context(db,uid,task_type,task_id)
   recommendations=service.current_view(db,uid)
   key=task_type+':'+str(task_id)
   context['recommendation']=next((item for item in recommendations['items'] if item['key']==key),None)
   context['batch_id']=recommendations.get('batch_id')
   current=db.get(StateCurrent,uid)
   snapshot=db.get(StateSnapshot,current.snapshot_id) if current else None
   context['state']={'pressure':snapshot.pressure,'energy':snapshot.energy,'difficulty':snapshot.difficulty} if snapshot else None
   return context
 except AIError as e:return error_response(request,e)

class Refresh(BaseModel):
 request_id:UUID
 expected_snapshot_id:UUID|None=None
class Correction(BaseModel):
 expected_version:int=Field(ge=1)
 keyword:str=Field(min_length=1,max_length=30)
 quadrants:list[__import__("typing").Literal["投入区","降噪区","激活区","修复区"]]=Field(min_length=1,max_length=4)
@router.get('/recommendations')
def view(request:Request):
 try:
  uid=user_id(request)
  with request.app.state.database.transaction() as db: return service.current_view(db,uid)
 except AIError as e:return error_response(request,e)

@router.post('/refresh')
async def refresh(request:Request):
 same_origin(request)
 try:
  uid=await run_in_threadpool(user_id,request);data=Refresh.model_validate_json(await request.body())
  await run_in_threadpool(service.refresh,request.app.state.database,request.app.state.settings,uid,data.request_id,data.expected_snapshot_id)
  return await run_in_threadpool(view,request)
 except ValidationError:return JSONResponse({'error':'请求编号无效'},422)
 except AIError as e:return error_response(request,e)

@router.patch('/task-analyses/{analysis_id}')
async def correct(request:Request,analysis_id:UUID):
 same_origin(request)
 try:
  uid=await run_in_threadpool(user_id,request);data=Correction.model_validate_json(await request.body())
  def apply():
   with request.app.state.database.transaction() as db:
    lock_user(db,uid);analysis=db.get(TaskAnalysis,analysis_id)
    if not analysis or analysis.user_id!=uid:raise AIError('not_found','任务分析不存在',404)
    live,_=service.candidates(db,uid)
    if analysis.target_key not in live or live[analysis.target_key]['fingerprint']!=analysis.fingerprint or analysis.version!=data.expected_version:raise AIError('stale','任务分析已过期，请先重新分析',409)
    analysis.override={**analysis.features,**data.model_dump(exclude={'expected_version'})};analysis.version+=1
   return {'saved':True,'message':'已修正，请刷新任务结果'}
  return await run_in_threadpool(apply)
 except ValidationError:return JSONResponse({'error':'修正字段无效'},422)
 except AIError as e:return error_response(request,e)
