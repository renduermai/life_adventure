"""Persistent owner-scoped life layers, modes, and original scene templates."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from app.modules.ai_gateway.security import AIError
from app.modules.identity.models import User
from app.modules.identity.service import lock_user
from .later_models import (ActiveLifeScene, LayerExperience, LayerExperienceRevision,
                           LifeScene, LifeSceneRevision, OperatingMode, OperatingModeHistory)
from .later_schemas import ExperienceInput, SceneInput

LIFE_LAYERS=('生存基本盘','生活秩序','精神生活','职业发展','长期发展')
NEED_LAYERS=('生理','安全','归属与爱','尊重','自我实现')
MODES=('green','yellow','red','blue')

def stamp(): return datetime.now(timezone.utc)

def exp_snapshot(row):
    data={k:getattr(row,k) for k in ('id','model','layer','occurred_on','event','experience','recommendation','notes','source','version','created_at','updated_at')}
    return {k:(v.isoformat() if hasattr(v,'isoformat') else str(v) if isinstance(v,UUID) else v) for k,v in data.items()}

def scene_snapshot(row):
    data={k:deepcopy(getattr(row,k)) for k in ('id','name','daily_slots','weekly_rhythm','version','created_at','updated_at')}
    return {k:(v.isoformat() if hasattr(v,'isoformat') else str(v) if isinstance(v,UUID) else v) for k,v in data.items()}

def experience_list(database,uid,model,layer):
    if (model,layer) not in [('life',x) for x in LIFE_LAYERS]+[('need',x) for x in NEED_LAYERS]:
        raise AIError('invalid_input','层次无效',422)
    with database.transaction() as db:
        rows=list(db.scalars(select(LayerExperience).where(LayerExperience.user_id==uid,LayerExperience.model==model,LayerExperience.layer==layer,LayerExperience.deleted_at.is_(None)).order_by(LayerExperience.occurred_on.desc(),LayerExperience.created_at.desc()).limit(100)))
        return {'items':[exp_snapshot(x) for x in rows]}

def experience_history(database,uid,eid):
    with database.transaction() as db:
        row=db.scalar(select(LayerExperience).where(LayerExperience.id==eid,LayerExperience.user_id==uid))
        if not row: raise AIError('not_found','经验不存在或无权访问',404)
        revisions=list(db.scalars(select(LayerExperienceRevision).where(LayerExperienceRevision.experience_id==eid,LayerExperienceRevision.user_id==uid).order_by(LayerExperienceRevision.version.desc()).limit(50)))
        return {'items':[{'version':x.version,'action':x.action,'snapshot':x.snapshot,'created_at':x.created_at} for x in revisions]}

def save_experience(database,uid,data:ExperienceInput,eid=None):
    with database.transaction() as db:
        lock_user(db,uid)
        row=db.scalar(select(LayerExperience).where(LayerExperience.id==eid,LayerExperience.user_id==uid)) if eid else None
        if eid and (row is None or row.deleted_at): raise AIError('not_found','经验不存在或无权访问',404)
        if row and (row.model!=data.model or row.layer!=data.layer): raise AIError('invalid_input','编辑时不能变更经验所属层次',422)
        now=stamp()
        if row:
            action='update';row.version+=1;row.occurred_on=data.occurred_on;row.event=data.event.strip();row.experience=data.experience.strip();row.recommendation=data.recommendation.strip();row.notes=data.notes.strip();row.updated_at=now
        else:
            action='create';row=LayerExperience(id=uuid4(),user_id=uid,model=data.model,layer=data.layer,occurred_on=data.occurred_on,event=data.event.strip(),experience=data.experience.strip(),recommendation=data.recommendation.strip(),notes=data.notes.strip(),source='user',version=1,created_at=now,updated_at=now);db.add(row);db.flush()
        db.add(LayerExperienceRevision(experience_id=row.id,user_id=uid,version=row.version,action=action,snapshot=exp_snapshot(row)))
        return exp_snapshot(row)

def delete_experience(database,uid,eid):
    with database.transaction() as db:
        lock_user(db,uid);row=db.scalar(select(LayerExperience).where(LayerExperience.id==eid,LayerExperience.user_id==uid,LayerExperience.deleted_at.is_(None)))
        if not row: raise AIError('not_found','经验不存在或无权访问',404)
        row.deleted_at=stamp();row.version+=1;row.updated_at=stamp()
        db.add(LayerExperienceRevision(experience_id=row.id,user_id=uid,version=row.version,action='delete',snapshot=exp_snapshot(row)))
        return {'deleted':True,'id':eid}

def relevant_experiences(db,uid,layers):
    layers=list(dict.fromkeys([x for x in layers if x in (*LIFE_LAYERS,*NEED_LAYERS)]))
    if not layers:return []
    rows=list(db.scalars(select(LayerExperience).where(LayerExperience.user_id==uid,LayerExperience.layer.in_(layers),LayerExperience.deleted_at.is_(None)).order_by(LayerExperience.occurred_on.desc(),LayerExperience.created_at.desc()).limit(12)))
    result=[];remaining=4000
    for row in rows:
        item={'model':row.model,'layer':row.layer,'occurred_on':str(row.occurred_on),'event':row.event[:220],'experience':row.experience[:300],'recommendation':row.recommendation[:220]}
        size=sum(len(str(v)) for v in item.values())
        if size>remaining:continue
        result.append(item);remaining-=size
    return result

def public_mode(row):
    if row is None:return {'follows_ai':True,'actual_mode':None,'suggested_mode':None,'reason':'','version':0,'history':[]}
    return {'follows_ai':row.follows_ai,'actual_mode':row.actual_mode,'suggested_mode':row.suggested_mode,'reason':row.reason,'version':row.version}

def mode_read(database,uid):
    with database.transaction() as db:
        row=db.get(OperatingMode,uid);result=public_mode(row)
        history=list(db.scalars(select(OperatingModeHistory).where(OperatingModeHistory.user_id==uid).order_by(OperatingModeHistory.version.desc()).limit(20)))
        result['history']=[{'version':x.version,'action':x.action,'actual_mode':x.actual_mode,'suggested_mode':x.suggested_mode,'follows_ai':x.follows_ai,'reason':x.reason,'created_at':x.created_at} for x in history]
        return result

def record_mode(db,uid,action,actual,suggested,follows,reason):
    row=db.get(OperatingMode,uid)
    if row is None:
        row=OperatingMode(user_id=uid,follows_ai=follows,actual_mode=actual,suggested_mode=suggested,reason=reason,version=1,updated_at=stamp());db.add(row);db.flush()
    else:
        if (row.actual_mode,row.suggested_mode,row.follows_ai,row.reason)==(actual,suggested,follows,reason):return row
        row.version+=1;row.actual_mode=actual;row.suggested_mode=suggested;row.follows_ai=follows;row.reason=reason;row.updated_at=stamp()
    db.add(OperatingModeHistory(user_id=uid,version=row.version,action=action,actual_mode=row.actual_mode,suggested_mode=row.suggested_mode,follows_ai=row.follows_ai,reason=row.reason))
    return row

def apply_analysis_mode(db,uid,analysis):
    result=analysis.result or {};suggested=result.get('suggested_mode');suggested=suggested if suggested in MODES else None
    reason=(result.get('core_conflict') or '')[:240]
    row=db.get(OperatingMode,uid);follows=True if row is None else row.follows_ai
    actual=(suggested if follows else row.actual_mode) if suggested else (row.actual_mode if row else None)
    record_mode(db,uid,'ai_analysis',actual,suggested,follows,reason)
    row=db.get(OperatingMode,uid);row.analysis_id=analysis.id

def mode_choose(database,uid,mode,follow=False):
    with database.transaction() as db:
        lock_user(db,uid);row=db.get(OperatingMode,uid)
        if follow:
            suggested=row.suggested_mode if row else None
            actual=suggested or (row.actual_mode if row else None)
            result=record_mode(db,uid,'follow_ai',actual,suggested,True,row.reason if row else '')
        else:
            result=record_mode(db,uid,'manual_select',mode,row.suggested_mode if row else None,False,row.reason if row else '')
        return public_mode(result)

def scene_list(database,uid):
    with database.transaction() as db:
        rows=list(db.scalars(select(LifeScene).where(LifeScene.user_id==uid,LifeScene.deleted_at.is_(None)).order_by(LifeScene.created_at,LifeScene.id)))
        active=db.get(ActiveLifeScene,uid)
        if active and not any(x.id==active.scene_id for x in rows):active=None
        if active is None and rows:
            active=ActiveLifeScene(user_id=uid,scene_id=rows[0].id);db.merge(active)
        return {'items':[scene_snapshot(x) for x in rows],'active_id':str(active.scene_id) if active else None}

def scene_current(database,uid,timezone_name,at=None):
    zone=ZoneInfo(timezone_name);local=(at or datetime.now(zone)).astimezone(zone);weekday=local.weekday();minute=local.hour*60+local.minute
    data=scene_list(database,uid);scene=next((x for x in data['items'] if x['id']==data['active_id']),None)
    if not scene:return {**data,'timezone':timezone_name,'local_now':local.isoformat(),'minute_of_day':minute,'day_progress':round((minute/1440)*100,2),'current':None,'next':None}
    slots=scene['daily_slots'];chronological=sorted(slots,key=lambda x:x['start']);absolute=[]
    for index,slot in enumerate(chronological):
        start=int(slot['start'][:2])*60+int(slot['start'][3:]);end=None
        if slot.get('end'):end=int(slot['end'][:2])*60+int(slot['end'][3:])+1440*slot.get('end_day_offset',0)
        elif index+1<len(chronological):end=int(chronological[index+1]['start'][:2])*60+int(chronological[index+1]['start'][3:])
        absolute.append((start,end,slot))
        if slot.get('end') and slot.get('end_day_offset')==1:absolute.append((start-1440,end-1440,slot))
    current=None;current_start=-1;next_item=None
    for start,end,slot in absolute:
        if start<=minute and (end is None or minute<end) and (current is None or start>current_start):current=slot;current_start=start
        elif start>minute and next_item is None:next_item=slot
    if next_item is None and slots:next_item=slots[0]
    weekly=next((x for x in scene['weekly_rhythm'] if x['weekday']==weekday and x['period']==('daytime' if 6<=local.hour<17 else 'evening' if local.hour>=17 else 'daytime')),None)
    return {**data,'timezone':timezone_name,'local_now':local.isoformat(),'minute_of_day':minute,'day_progress':round(minute/1440*100,2),'current':current,'next':next_item,'weekly_current':weekly}

def scene_select(database,uid,scene_id):
    with database.transaction() as db:
        lock_user(db,uid);row=db.scalar(select(LifeScene).where(LifeScene.id==scene_id,LifeScene.user_id==uid,LifeScene.deleted_at.is_(None)))
        if not row:raise AIError('not_found','场景不存在或无权访问',404)
        db.merge(ActiveLifeScene(user_id=uid,scene_id=scene_id));return {'active_id':scene_id}

def save_scene(database,uid,data:SceneInput,scene_id=None,copy_id=None):
    with database.transaction() as db:
        lock_user(db,uid);now=stamp()
        if copy_id:
            original=db.scalar(select(LifeScene).where(LifeScene.id==copy_id,LifeScene.user_id==uid,LifeScene.deleted_at.is_(None)))
            if not original:raise AIError('not_found','场景不存在或无权访问',404)
            row=LifeScene(id=uuid4(),user_id=uid,name=data.name,daily_slots=deepcopy(original.daily_slots),weekly_rhythm=deepcopy(original.weekly_rhythm),version=1,created_at=now,updated_at=now);action='copy';db.add(row);db.flush()
        elif scene_id:
            row=db.scalar(select(LifeScene).where(LifeScene.id==scene_id,LifeScene.user_id==uid,LifeScene.deleted_at.is_(None)))
            if not row:raise AIError('not_found','场景不存在或无权访问',404)
            row.version+=1;row.name=data.name;row.daily_slots=data.daily_slots;row.weekly_rhythm=data.weekly_rhythm;row.updated_at=now;action='update'
        else:
            row=LifeScene(id=uuid4(),user_id=uid,name=data.name,daily_slots=data.daily_slots,weekly_rhythm=data.weekly_rhythm,version=1,created_at=now,updated_at=now);db.add(row);db.flush();action='create'
        db.add(LifeSceneRevision(scene_id=row.id,user_id=uid,version=row.version,action=action,snapshot=scene_snapshot(row)))
        if db.get(ActiveLifeScene,uid) is None:db.add(ActiveLifeScene(user_id=uid,scene_id=row.id))
        return scene_snapshot(row)

def scene_history(database,uid,scene_id):
    with database.transaction() as db:
        row=db.scalar(select(LifeScene.id).where(LifeScene.id==scene_id,LifeScene.user_id==uid))
        if row is None:raise AIError('not_found','场景不存在或无权访问',404)
        revisions=list(db.scalars(select(LifeSceneRevision).where(LifeSceneRevision.scene_id==scene_id,LifeSceneRevision.user_id==uid).order_by(LifeSceneRevision.version.desc()).limit(50)))
        return {'items':[{'version':x.version,'action':x.action,'snapshot':x.snapshot,'created_at':x.created_at} for x in revisions]}

def delete_scene(database,uid,scene_id):
    with database.transaction() as db:
        lock_user(db,uid);row=db.scalar(select(LifeScene).where(LifeScene.id==scene_id,LifeScene.user_id==uid,LifeScene.deleted_at.is_(None)))
        if not row:raise AIError('not_found','场景不存在或无权访问',404)
        row.deleted_at=stamp();row.version+=1;row.updated_at=stamp();db.add(LifeSceneRevision(scene_id=row.id,user_id=uid,version=row.version,action='delete',snapshot=scene_snapshot(row)))
        active=db.get(ActiveLifeScene,uid)
        if active and active.scene_id==scene_id:
            db.delete(active);other=db.scalar(select(LifeScene).where(LifeScene.user_id==uid,LifeScene.deleted_at.is_(None),LifeScene.id!=scene_id).order_by(LifeScene.created_at).limit(1))
            if other:db.add(ActiveLifeScene(user_id=uid,scene_id=other.id))
        return {'deleted':True,'id':scene_id}

def scene_history_route(database,uid,scene_id): return scene_history(database,uid,scene_id)
