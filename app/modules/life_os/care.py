"""Owner-locked care templates and independent local-date recovery records."""
from datetime import date, datetime, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
from typing import Literal
from pydantic import Field, field_validator
from sqlalchemy import Date, ForeignKey, JSON, select
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.modules.identity.models import User
from app.modules.identity.service import lock_user
from app.modules.ai_gateway.security import AIError
from .schemas import Strict

class Care(Base):
    __tablename__='life_os_care'
    user_id: Mapped[UUID]=mapped_column(ForeignKey('users.id'),primary_key=True)
    data: Mapped[dict]=mapped_column(JSON)
    version: Mapped[int]=mapped_column(default=1)
class CareDay(Base):
    __tablename__='life_os_care_days'
    user_id: Mapped[UUID]=mapped_column(ForeignKey('users.id'),primary_key=True)
    day: Mapped[date]=mapped_column(Date,primary_key=True)
    data: Mapped[dict]=mapped_column(JSON)
class Stage(Strict):
    title: str=Field(min_length=1,max_length=80)
    items: list[str]=Field(max_length=30)
    @field_validator('title')
    @classmethod
    def title_valid(cls,v):
        if not v.strip() or '\x00' in v:raise ValueError('阶段名称无效')
        return v.strip()
    @field_validator('items')
    @classmethod
    def valid(cls,v):
        if any(not x.strip() or len(x)>160 or '\x00' in x for x in v):raise ValueError('事项内容无效')
        return v
class Edit(Strict):
    version: int=Field(ge=0,strict=True)
    items: list[str]=Field(max_length=50)
    stages: list[Stage]=Field(max_length=20)
    @field_validator('items')
    @classmethod
    def valid(cls,v):return Stage.valid(v)
class Check(Strict):
    day: date
    item_id: UUID
    checked: bool=Field(strict=True)
class Feedback(Strict):
    day: date
    text: str=Field(max_length=1000)
DEFAULT_ITEMS=['保证必要睡眠','正常吃饭、喝水','刷牙洗脸，维持基本卫生','简单处理垃圾与脏衣服','遵医嘱照顾身体','与外界保持一点联系']
DEFAULT_STAGES=[{'title':t,'items':i} for t,i in [('停止下坠',['正常吃饭','洗澡、换衣服','清理垃圾','保证必要睡眠']),('恢复环境',['整理床铺、桌面','洗衣服','补充生活用品']),('恢复快乐',['身体允许时散步','听音乐','联系朋友']),('恢复行动',['从一个小任务开始','适当恢复学习']),('恢复发展',['逐步回到工作','技术学习','身体允许时恢复运动与兴趣'])]]
def today(db,uid):return datetime.now(ZoneInfo(db.get(User,uid).timezone)).date()
def items(values):return [{'id':str(uuid4()),'title':x.strip()} for x in values]
def progress(data):
    count=sum(bool(x['checked']) for x in data['items']);total=len(data['items']);pct=round(count/total*100,1) if total else None
    band=None if pct is None else 0 if pct<30 else 1 if pct<60 else 2 if pct<90 else 3
    return {'done':count,'total':total,'percent':pct,'band':band,'face':['😟','😐','🙂','😊'][band] if band is not None else '—'}
def load(database,uid,day=None):
    with database.transaction() as db:
        row=db.get(Care,uid);day=day or today(db,uid);record=db.get(CareDay,(uid,day))
        data=record.data if record else {'items':[dict(x,checked=False) for x in (row.data['items'] if row else [])],'successes':[],'feedback':''}
        return {'day':str(day),'today':str(today(db,uid)),'version':row.version if row else 0,'template':row.data if row else {'items':[],'stages':[],'history':[]},'record':data,'progress':progress(data),'defaults':{'items':DEFAULT_ITEMS,'stages':DEFAULT_STAGES}}
def save(database,uid,edit):
    with database.transaction() as db:
        lock_user(db,uid);row=db.get(Care,uid)
        if edit.version!=(row.version if row else 0):raise AIError('version_conflict','内容已变化，请刷新后重试',409)
        previous=row.data if row else None
        old={x['title']:x['id'] for x in previous['items']} if previous else {}
        configured=[{'id':old.get(x.strip(),str(uuid4())),'title':x.strip()} for x in edit.items]
        if len({x['title'] for x in configured})!=len(configured):raise AIError('invalid_input','清单事项不能重复',422)
        history=list(previous.get('history',[])) if previous else []
        if previous:history.append({'version':row.version,'items':previous['items'],'stages':previous['stages'],'at':datetime.now(timezone.utc).isoformat()})
        data={'items':configured,'stages':[x.model_dump() for x in edit.stages],'history':history}
        if row:row.data=data;row.version+=1
        else:db.add(Care(user_id=uid,data=data,version=1))
        day=today(db,uid);record=db.get(CareDay,(uid,day))
        if record:
            snapshot=dict(record.data);existing={x['id']:x for x in snapshot['items']};snapshot['archived_items']=snapshot.get('archived_items',[])+[x for x in snapshot['items'] if x['id'] not in {i['id'] for i in configured}];snapshot['items']=[dict(x,checked=existing.get(x['id'],{}).get('checked',False)) for x in configured];record.data=snapshot
    return load(database,uid)
def check(database,uid,command):
    with database.transaction() as db:
        lock_user(db,uid)
        if command.day!=today(db,uid):raise AIError('day_changed','日期已变化，请刷新后勾选今天的清单',409)
        row=db.get(Care,uid)
        if not row:raise AIError('not_found','请先保存生活保障清单',404)
        record=db.get(CareDay,(uid,command.day));data=dict(record.data) if record else {'items':[dict(x,checked=False) for x in row.data['items']],'successes':[],'feedback':''}
        data['items']=[dict(x) for x in data['items']];target=next((x for x in data['items'] if x['id']==str(command.item_id)),None)
        if not target:raise AIError('not_found','事项不存在或已修改，请刷新',404)
        from .models import Analysis, Message
        analysis=db.scalar(select(Analysis).join(Message,Analysis.message_id==Message.id).where(Analysis.user_id==uid,Analysis.status=='succeeded').order_by(Message.created_at.desc(),Analysis.created_at.desc()).limit(1))
        reference={'analysis_id':str(analysis.id),'ai_summary':(analysis.result.get('reply') or '')[:600],'state':{k:analysis.result.get(k) for k in ('energy','bandwidth','order')}} if analysis else None
        before=progress(data);target['checked']=command.checked;after=progress(data)
        reached={s['band'] for s in data['successes']}
        if after['band'] is not None and after['band']>0 and after['band'] not in reached and after['done']>before['done']:
            data['successes']=data['successes']+[{'analysis_reference':reference,'band':after['band'],'from':before,'to':after,'completed':[x['title'] for x in data['items'] if x['checked']],'at':datetime.now(timezone.utc).isoformat(),'summary':'真实清单完成进度发生变化；不代表心理状态判断。'}]
        if record:record.data=data
        else:db.add(CareDay(user_id=uid,day=command.day,data=data))
    return load(database,uid,command.day)
def feedback(database,uid,command):
    with database.transaction() as db:
        lock_user(db,uid);record=db.get(CareDay,(uid,command.day))
        if not record:raise AIError('not_found','该日期没有实际清单记录',404)
        record.data=dict(record.data,feedback=command.text)
    return load(database,uid,command.day)
def recovery_context(db,uid):
    from .later_models import OperatingMode
    mode=db.get(OperatingMode,uid);row=db.get(Care,uid)
    if not mode or mode.actual_mode!='blue' or not row:return []
    return [{'title':s['title'],'items':s['items'][:5]} for s in row.data['stages'][:5]]
