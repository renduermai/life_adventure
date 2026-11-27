"""Problem bookkeeping; all callers scope by owner and serialize mutations."""
import hashlib
import json
import unicodedata
from datetime import datetime,timezone
from uuid import UUID,uuid4,uuid5
from sqlalchemy import select,func,and_,or_,exists,delete
from sqlalchemy.dialects.postgresql import distinct_on
from app.modules.ai_gateway.security import AIError
from app.modules.identity.service import lock_user
from app.modules.distractions.models import DistractionNote
from app.modules.distractions.service import get as get_note
from .models import Message,Analysis
from .problem_schemas import EventProposal
from pydantic import ValidationError
from .problem_models import Problem,LifeEvent,EventSource,EventProblem,Experience,ProblemHistory

def now():return datetime.now(timezone.utc)
def key(name):return ''.join(unicodedata.normalize('NFKC',name).casefold().split())
def values(row):
    fields=('id','name','mechanism','notes','manual_fields','version','deleted_at','merged_into') if isinstance(row,Problem) else ('id','title','occurred_at','status','version','deleted_at')
    return json.loads(json.dumps({k:getattr(row,k) for k in fields},default=str))
def get_problem(db,uid,pid):
    p=db.scalar(select(Problem).where(Problem.id==pid,Problem.user_id==uid,Problem.deleted_at.is_(None)))
    if not p:raise AIError('not_found','问题不存在或无权访问',404)
    return p
def get_event(db,uid,eid):
    e=db.scalar(select(LifeEvent).where(LifeEvent.id==eid,LifeEvent.user_id==uid,LifeEvent.deleted_at.is_(None)))
    if not e:raise AIError('not_found','事件不存在或无权访问',404)
    return e

def fingerprint(action,target,data):return hashlib.sha256(json.dumps([action,str(target),data.model_dump(mode='json')],sort_keys=True).encode()).hexdigest()
def duplicate(db,uid,action,target,data):
    old=db.scalar(select(ProblemHistory).where(ProblemHistory.user_id==uid,ProblemHistory.request_id==data.request_id))
    if old:
        if old.fingerprint!=fingerprint(action,target,data):raise AIError('request_conflict','操作编号已用于其他内容',409)
        return old.after

def audit(db,uid,target,action,rid,before,after,fingerprint_value='ai'):
    db.add(ProblemHistory(user_id=uid,target_id=target,action=action,request_id=rid,fingerprint=fingerprint_value,before=before,after=after))

def valid_event():
    return exists(select(EventSource.id).where(EventSource.event_id==LifeEvent.id,EventSource.user_id==LifeEvent.user_id,or_(EventSource.message_id.is_not(None),exists(select(DistractionNote.id).where(DistractionNote.id==EventSource.note_id,DistractionNote.user_id==EventSource.user_id,DistractionNote.deleted_at.is_(None))))))

def listing(db,uid,offset=0):
    counts=select(EventProblem.problem_id,func.count().label('count'),func.max(LifeEvent.occurred_at).label('last')).join(LifeEvent,and_(LifeEvent.id==EventProblem.event_id,LifeEvent.user_id==EventProblem.user_id)).where(LifeEvent.user_id==uid,LifeEvent.deleted_at.is_(None),LifeEvent.status=='confirmed',valid_event()).group_by(EventProblem.problem_id).subquery()
    rows=db.execute(select(Problem,func.coalesce(counts.c.count,0),counts.c.last).outerjoin(counts,counts.c.problem_id==Problem.id).where(Problem.user_id==uid,Problem.deleted_at.is_(None)).order_by(func.coalesce(counts.c.count,0).desc(),counts.c.last.desc().nullslast(),Problem.created_at.desc(),Problem.id).offset(offset).limit(21)).all()
    return {'items':[values(p)|{'count':count,'last_occurred_at':last} for p,count,last in rows[:20]],'next_offset':offset+20 if len(rows)>20 else None}

def notes(db,uid,offset=0,q=''):
    query=select(DistractionNote).where(DistractionNote.user_id==uid,DistractionNote.deleted_at.is_(None))
    if q:query=query.where(DistractionNote.content.contains(q,autoescape=True))
    rows=list(db.scalars(query.order_by(DistractionNote.created_at.desc(),DistractionNote.id.desc()).offset(offset).limit(21)))
    return {'items':[{'id':r.id,'content':r.content,'created_at':r.created_at} for r in rows[:20]],'next_offset':offset+20 if len(rows)>20 else None}

def selected_notes(db,uid,note_ids):
    ids=list(dict.fromkeys(note_ids))
    rows={r.id:r for r in db.scalars(select(DistractionNote).where(DistractionNote.user_id==uid,DistractionNote.id.in_(ids),DistractionNote.deleted_at.is_(None)))}
    if len(rows)!=len(ids):raise AIError('not_found','部分杂念不存在、已删除或无权访问',404)
    return [rows[nid] for nid in ids]

def context(db,uid,note_ids,recent_ids):
    problem_rows=listing(db,uid)['items']
    # Explicitly selected notes only; no background scan or mutation of notes.
    selected=[]
    for n in selected_notes(db,uid,note_ids):
        selected.append({'id':str(n.id),'content':n.content,'version':n.version})
    if len(json.dumps(selected,ensure_ascii=False))>120000:raise AIError('context_too_large','所选杂念超过本轮模型上下文预算，请分批分析',422)
    ev=list(db.scalars(select(LifeEvent).where(LifeEvent.user_id==uid,LifeEvent.deleted_at.is_(None),valid_event()).order_by(LifeEvent.occurred_at.desc(),LifeEvent.id.desc()).limit(10)))
    linked=list(db.scalars(select(LifeEvent).join(EventSource,and_(EventSource.event_id==LifeEvent.id,EventSource.user_id==LifeEvent.user_id)).where(LifeEvent.user_id==uid,LifeEvent.deleted_at.is_(None),EventSource.message_id.in_(recent_ids))))
    events={e.id:e for e in linked+ev}
    problem_context=[{k:r[k] for k in ('id','name','mechanism','notes','version')} for r in problem_rows]
    # Bound per-record text as well as overall payload; summaries don't imply success.
    for p in problem_context:
        p['id']=str(p['id']);p['mechanism']=p['mechanism'][:180];p['notes']=p['notes'][:180]
    event_context=[]
    for e in events.values():
        sources=list(db.scalars(select(EventSource.message_id).where(EventSource.user_id==uid,EventSource.event_id==e.id,EventSource.message_id.is_not(None))))
        exp=list(db.scalars(select(Experience).where(Experience.user_id==uid,Experience.event_id==e.id).order_by(Experience.created_at.desc()).limit(2)))
        event_context.append({'id':str(e.id),'title':e.title,'date':e.occurred_at.isoformat(),'status':e.status,'version':e.version,'message_ids':list(map(str,sources))[-20:],'note_ids':list(map(str,db.scalars(select(EventSource.note_id).where(EventSource.user_id==uid,EventSource.event_id==e.id,EventSource.note_id.is_not(None))))),'experience':[{'kind':x.kind,'text':x.text[:180],'outcome':x.outcome} for x in exp]})
    result={'problems':[],'events':[],'selected_notes':selected}
    # The shared Gateway allows 24k characters. Keep this whole extension under 7k.
    for idx in range(max(len(problem_context),len(event_context))):
        for kind,candidates in [('events',event_context),('problems',problem_context)]:
            if idx>=len(candidates):continue
            result[kind].append(candidates[idx])
            if len(json.dumps({'problems':result['problems'],'events':result['events']},ensure_ascii=False))>7000:result[kind].pop()
    return result

def validate_notes(db,uid,ctx):
    for source in ctx['selected_notes']:
        row=db.scalar(select(DistractionNote).where(DistractionNote.id==UUID(source['id']),DistractionNote.user_id==uid,DistractionNote.deleted_at.is_(None)))
        if row is None or row.version!=source['version']:raise AIError('source_changed','杂念来源已变化，本次结果未发布',409)

def validate(proposal,ctx,content):
    if proposal is None:return
    if proposal.evidence_quote not in content:raise AIError('invalid_evidence','事件依据不在本轮原文中',502)
    for quote in (proposal.action_quote,proposal.feedback_quote):
        if quote and quote not in content:raise AIError('invalid_evidence','行动或效果缺少原文依据',502)
    if proposal.existing_event_id and str(proposal.existing_event_id) not in {x['id'] for x in ctx['events']}:raise AIError('invalid_sources','事件引用不在授权上下文中',502)
    allowed={x['id'] for x in ctx['problems']}
    for p in proposal.problems:
        if not key(p.name):raise AIError('invalid_schema','问题名称不能为空',502)
        if p.existing_id and str(p.existing_id) not in allowed:raise AIError('invalid_sources','问题引用不在授权上下文中',502)

def experience(db,uid,eid,kind,text,outcome='unknown',mid=None,quote=None,salt=''):
    if not text:return
    dedup=hashlib.sha256(json.dumps([str(eid),kind,text,str(mid),salt],ensure_ascii=False).encode()).hexdigest()
    if not db.scalar(select(Experience.id).where(Experience.user_id==uid,Experience.dedup_key==dedup)):
        db.add(Experience(user_id=uid,event_id=eid,kind=kind,text=text,outcome=outcome,source_message_id=mid,source_quote=quote,dedup_key=dedup))

def apply(db,uid,analysis,proposal,ctx):
    if proposal is None:return 'no_event'
    if isinstance(proposal,dict):
        try:proposal=EventProposal.model_validate(proposal)
        except ValidationError:raise AIError('invalid_schema','事件字段无效；核心分析已保存',502) from None
    message=db.get(Message,analysis.message_id)
    validate(proposal,ctx,message.content)
    # A source has one stable occurrence; reruns never create a new occurrence.
    source=db.scalar(select(EventSource).where(EventSource.user_id==uid,EventSource.message_id==message.id))
    if source:return 'already_linked'
    validate_notes(db,uid,ctx)
    problem_versions={x['id']:x['version'] for x in ctx['problems']}
    if proposal.existing_event_id:
        event=get_event(db,uid,proposal.existing_event_id)
        expected=next(x['version'] for x in ctx['events'] if x['id']==str(event.id))
        if event.version!=expected:raise AIError('source_changed','事件已手动修改，未覆盖',409)
    else:
        event=LifeEvent(user_id=uid,title=proposal.title,occurred_at=message.created_at,status='confirmed' if proposal.relation=='new' else 'pending')
        db.add(event);db.flush()
    db.add(EventSource(user_id=uid,event_id=event.id,message_id=message.id));db.flush()
    for item in proposal.problems:
        if item.existing_id:
            p=get_problem(db,uid,item.existing_id)
            if p.version!=problem_versions[str(p.id)]:raise AIError('source_changed','问题已被修改，未覆盖',409)
        else:
            p=db.scalar(select(Problem).where(Problem.user_id==uid,Problem.name_key==key(item.name)))
            if p and p.deleted_at:continue # deleted/merged names are not silently resurrected
            if not p:
                p=Problem(user_id=uid,name=item.name.strip(),name_key=key(item.name));db.add(p);db.flush()
                audit(db,uid,p.id,'ai_create',uuid5(analysis.id,str(p.id)+'create'),{},values(p))
        if not db.get(EventProblem,(event.id,p.id)):db.add(EventProblem(event_id=event.id,problem_id=p.id,user_id=uid))
        before=values(p)
        if item.mechanism and 'mechanism' not in p.manual_fields:p.mechanism=item.mechanism
        if values(p)!=before:
            p.version+=1
            audit(db,uid,p.id,'ai_mechanism',uuid5(analysis.id,str(p.id)+'mechanism'),before,values(p))
        experience(db,uid,event.id,'observation',item.observation,mid=message.id)
    experience(db,uid,event.id,'suggestion',analysis.result['feasible_action'],mid=message.id)
    experience(db,uid,event.id,'action',proposal.action_quote,mid=message.id,quote=proposal.action_quote or None)
    experience(db,uid,event.id,'feedback',proposal.feedback_quote,proposal.outcome,mid=message.id,quote=proposal.feedback_quote or None)
    return 'pending' if event.status=='pending' else 'succeeded'

def sync(database,uid,aid,proposal,ctx):
    try:
        with database.transaction() as db:
            lock_user(db,uid);row=db.get(Analysis,aid)
            if row is None or row.status != 'succeeded':return
            row.experience_status=apply(db,uid,row,proposal,ctx)
    except Exception as exc:
        code=exc.code if isinstance(exc,AIError) else 'experience_failed'
        with database.transaction() as db:
            row=db.get(Analysis,aid)
            if row is not None:row.experience_status='failed';row.experience_error=code
        # No private source or exception message is logged.
        import logging
        logging.getLogger('adventure_camp.life_os').warning('experience_sync_failed code=%s type=%s',code,type(exc).__name__)

def event_detail(db,uid,event):
    sources=[]
    for s in db.scalars(select(EventSource).where(EventSource.user_id==uid,EventSource.event_id==event.id)):
        if s.message_id:
            m=db.get(Message,s.message_id)
            sources.append({'id':s.id,'kind':'message','source_id':m.id,'content':m.content,'created_at':m.created_at})
        else:
            n=db.get(DistractionNote,s.note_id)
            sources.append({'id':s.id,'kind':'note','source_id':s.note_id,'content':n.content if n and not n.deleted_at else None,'created_at':n.created_at if n else None})
    mids=[s['source_id'] for s in sources if s['kind']=='message']
    snapshot=db.scalar(select(Analysis).where(Analysis.user_id==uid,Analysis.message_id.in_(mids),Analysis.status=='succeeded').order_by(Analysis.created_at.desc()).limit(1)) if mids else None
    states=list(db.scalars(select(Analysis).where(Analysis.user_id==uid,Analysis.message_id.in_(mids),Analysis.status=='succeeded').ext(distinct_on(Analysis.message_id)).order_by(Analysis.message_id,Analysis.created_at.desc(),Analysis.id.desc()))) if mids else []
    by_message={r.message_id:r.result for r in states}
    for source in sources:
        result=by_message.get(source['source_id']) if source['kind']=='message' else None
        source['state']={k:result[k] for k in ('energy','bandwidth','order','suggested_mode','feasible_action')} if result else None
    exps=[{k:getattr(x,k) for k in ('id','kind','text','outcome','source_message_id','source_quote','created_at')} for x in db.scalars(select(Experience).where(Experience.user_id==uid,Experience.event_id==event.id).order_by(Experience.created_at.asc(),Experience.id))]
    return values(event)|{'history':[{'action':h.action,'before':h.before,'after':h.after,'created_at':h.created_at} for h in db.scalars(select(ProblemHistory).where(ProblemHistory.user_id==uid,ProblemHistory.target_id==event.id).order_by(ProblemHistory.created_at.desc()).limit(50))],'sources':sources,'experiences':exps,'problem_ids':list(db.scalars(select(EventProblem.problem_id).where(EventProblem.user_id==uid,EventProblem.event_id==event.id))),'state':snapshot.result if snapshot else None,'effect_pending':not any(x['kind']=='feedback' for x in exps)}

def detail(db,uid,pid,offset):
    p=get_problem(db,uid,pid)
    events=list(db.scalars(select(LifeEvent).join(EventProblem,and_(EventProblem.event_id==LifeEvent.id,EventProblem.user_id==LifeEvent.user_id)).where(EventProblem.user_id==uid,EventProblem.problem_id==pid,LifeEvent.deleted_at.is_(None)).order_by(LifeEvent.occurred_at.desc(),LifeEvent.id.desc()).offset(offset).limit(21)))
    history=list(db.scalars(select(ProblemHistory).where(ProblemHistory.user_id==uid,ProblemHistory.target_id==pid).order_by(ProblemHistory.created_at.desc()).limit(50)))
    return {'problem':values(p),'events':[event_detail(db,uid,e) for e in events[:20]],'next_offset':offset+20 if len(events)>20 else None,'history':[{'action':r.action,'before':r.before,'after':r.after,'created_at':r.created_at} for r in history]}

def mutate(database,uid,action,target,data):
    with database.transaction() as db:
        lock_user(db,uid)
        old=duplicate(db,uid,action,target,data)
        if old is not None:return old
        before={};audit_target=target
        if action in ('edit_problem','delete_problem','merge'):
            p=get_problem(db,uid,target);before=values(p)
            if p.version!=data.expected_version:raise AIError('version_conflict','问题已变化，请刷新',409)
            if action=='edit_problem':
                normalized=key(data.name)
                if not normalized:raise AIError('invalid_input','问题名称不能为空',422)
                other=db.scalar(select(Problem.id).where(Problem.user_id==uid,Problem.name_key==normalized,Problem.id!=p.id))
                if other:raise AIError('name_conflict','同名问题已存在，请合并或换名',409)
                p.name=data.name.strip();p.name_key=normalized;p.mechanism=data.mechanism;p.notes=data.notes;p.manual_fields=['name','mechanism','notes']
            elif action=='delete_problem':p.deleted_at=now()
            else:
                target_problem=get_problem(db,uid,data.target_id)
                if p.id==target_problem.id:raise AIError('invalid_input','不能合并到自身',422)
                if target_problem.version!=data.target_version:raise AIError('version_conflict','目标问题已变化',409)
                links=list(db.scalars(select(EventProblem).where(EventProblem.user_id==uid,EventProblem.problem_id==p.id)))
                for link in links:
                    if not db.get(EventProblem,(link.event_id,target_problem.id)):db.add(EventProblem(event_id=link.event_id,problem_id=target_problem.id,user_id=uid))
                    db.delete(link)
                p.deleted_at=now();p.merged_into=target_problem.id
                target_before=values(target_problem);target_problem.version+=1
                audit(db,uid,target_problem.id,'merge_received',uuid5(data.request_id,'target'),target_before,values(target_problem)|{'merged_source':before})
            p.version+=1;db.flush();after=values(p)
        elif action=='edit_event':
            e=get_event(db,uid,target);before=values(e)
            if e.version!=data.expected_version:raise AIError('version_conflict','事件已变化',409)
            for pid in data.problem_ids:get_problem(db,uid,pid)
            e.title=data.title;e.occurred_at=data.occurred_at;e.status=data.status;e.version+=1
            db.execute(delete(EventProblem).where(EventProblem.user_id==uid,EventProblem.event_id==e.id))
            for pid in data.problem_ids:db.add(EventProblem(user_id=uid,event_id=e.id,problem_id=pid))
            after=values(e)|{'problem_ids':list(map(str,data.problem_ids))}
        elif action=='move_source':
            source=db.scalar(select(EventSource).where(EventSource.user_id==uid,EventSource.id==data.source_id))
            if not source:raise AIError('not_found','来源不存在或无权访问',404)
            origin=get_event(db,uid,source.event_id);audit_target=origin.id
            if origin.id!=data.expected_event_id or origin.version!=data.expected_version:raise AIError('version_conflict','来源归属已变化，请刷新后重试',409)
            before={'event_id':str(origin.id),'source_id':str(source.id)}
            if data.target_event_id:e=get_event(db,uid,data.target_event_id)
            else:
                if not data.title.strip():raise AIError('invalid_input','新事件需要名称',422)
                e=LifeEvent(user_id=uid,title=data.title,occurred_at=origin.occurred_at,status='confirmed');db.add(e);db.flush()
                for pid in db.scalars(select(EventProblem.problem_id).where(EventProblem.user_id==uid,EventProblem.event_id==origin.id)):db.add(EventProblem(event_id=e.id,problem_id=pid,user_id=uid))
            if e.id!=origin.id:
                if source.message_id:
                    for x in db.scalars(select(Experience).where(Experience.user_id==uid,Experience.source_message_id==source.message_id,Experience.event_id==origin.id)):x.event_id=e.id
                source.event_id=e.id;origin.version+=1;e.version+=1
            after={'event_id':str(e.id),'source_id':str(source.id)}
        elif action=='feedback':
            e=get_event(db,uid,target)
            # A command receipt makes repeated feedback submissions harmless.
            experience(db,uid,e.id,'action',data.action,salt=str(data.request_id))
            experience(db,uid,e.id,'feedback',data.feedback,data.outcome,salt=str(data.request_id))
            after={'saved':True,'event_id':str(e.id)}
        elif action=='import_note':
            n=get_note(db,uid,data.note_id)
            source=db.scalar(select(EventSource).where(EventSource.user_id==uid,EventSource.note_id==n.id))
            if source:raise AIError('source_linked','该杂念已有事件归属，请使用修正归属',409)
            for pid in data.problem_ids:get_problem(db,uid,pid)
            if data.event_id:e=get_event(db,uid,data.event_id)
            else:e=LifeEvent(user_id=uid,title=data.title,occurred_at=n.created_at,status='confirmed');db.add(e);db.flush()
            db.add(EventSource(user_id=uid,event_id=e.id,note_id=n.id));e.version+=1
            for pid in set(data.problem_ids):
                if not db.get(EventProblem,(e.id,pid)):db.add(EventProblem(user_id=uid,event_id=e.id,problem_id=pid))
            audit_target=e.id
            after={'event_id':str(e.id),'saved':True}
        else:raise AIError('invalid_action','操作无效',422)
        audit(db,uid,audit_target,action,data.request_id,before,after,fingerprint(action,target,data));db.flush()
        return after


def reusable(db,uid,analysis,selected_ids):
    """Never resend a note-derived reply/state after its note is unselected or deleted."""
    if not analysis:return False
    for source in analysis.note_scope or []:
        if source['id'] not in set(map(str,selected_ids)):return False
        note=db.scalar(select(DistractionNote).where(DistractionNote.id==UUID(source['id']),DistractionNote.user_id==uid,DistractionNote.deleted_at.is_(None)))
        if note is None or note.version!=source['version']:return False
    return True
