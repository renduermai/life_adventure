import json,os
from datetime import datetime,timedelta,timezone
from uuid import uuid4,UUID
from zoneinfo import ZoneInfo
import pytest
from sqlalchemy import select,create_engine
from sqlalchemy.orm import Session
from app.modules.life_os.attractors import Output
from app.modules.life_os.models import Message
from app.modules.life_os.problem_models import LifeEvent,EventSource
from app.modules.ai_gateway.service import AIService
from app.modules.ai_gateway.security import AIError
from app.modules.ai_gateway.models import AIConfig
from app.core.config import load_settings,postgres_url
from test_distractions_postgres import notes
from test_tasks_postgres import task_engine
H={'Origin':'http://testserver'}
def seed(s,uid,days=0):
 with s.begin() as db:
  m=Message(user_id=uid,request_id=uuid4(),content='合成事件：学习受挫时，先听音乐再整理桌面。');db.add(m);db.flush()
  e=LifeEvent(user_id=uid,title='合成恢复事件',occurred_at=datetime.now(timezone.utc)-timedelta(days=days),status='confirmed',version=1);db.add(e);db.flush();db.add(EventSource(user_id=uid,event_id=e.id,message_id=m.id));return str(e.id),str(m.id)
def payload():
 today=datetime.now(ZoneInfo('Asia/Shanghai')).date();return {'start':str(today-timedelta(days=14)),'end':str(today),'consent_external':True,'note_ids':[],'full':False}
def response_for(events):
 return Output(patterns=[{'name':'音乐辅助恢复观察','description':'学习受挫后尝试轻量恢复','mechanism':'音乐可能帮助开始行动','intervention':'先做一个低负荷动作','links':[{'event_id':e['id'],'source_id':e['sources'][0]['id'],'quote':'先听音乐再整理桌面','strength':'medium','reason':'用户报告了该行动'} for e in events]}],current_pattern=None,current_event_id=None,insufficient_reason='')
def test_evidence_cache_incremental_failure_and_owner(notes,monkeypatch):
 c,s,uid,other,app=notes;seed(s,uid);seen=[];all_events=[]
 def model(self,user,purpose,messages,request_id,**kw):
  data=json.loads(messages[1]['content']);seen.append(data);all_events.extend(e for e in data['events'] if e['id'] not in {x['id'] for x in all_events});return {'content':response_for(all_events),'usage':None}
 monkeypatch.setattr(AIService,'generate',model);p=payload();url='/api/life-os/attractors/'
 first=c.post(url+'analyze',headers=H,json=p);assert first.status_code==200,first.text
 assert c.post(url+'analyze',headers=H,json=p).json()['cached'];assert len(seen)==1
 eid=first.json()['result']['patterns'][0]['links'][0]['event_id'];assert c.post(url+'events/'+eid,headers=H,json=p).json()['sources'][0]['text'].startswith('合成事件')
 seed(s,uid);second=c.post(url+'analyze',headers=H,json=p);assert second.status_code==200,second.text
 assert second.json()['strategy']=='incremental' and len(seen[-1]['events'])==1
 def bad(*a,**k):raise AIError('output_truncated','合成截断',502)
 monkeypatch.setattr(AIService,'generate',bad);assert c.post(url+'analyze',headers=H,json=p|{'full':True}).status_code==502
 r=c.post(url+'read',headers=H,json=p).json();assert r['current']['id']==second.json()['id'] and r['attempt']['error_code']=='output_truncated'
 c.cookies.set('camp_session',str(other));assert c.post(url+'read',headers=H,json=p).json()['current'] is None
 assert c.post(url+'events/'+eid,headers=H,json=p).status_code==404
 c.cookies.clear();assert c.post(url+'read',headers=H,json=p).status_code==401

def test_attractor_live(notes,monkeypatch):
 if os.getenv('LIFE_OS_LIVE')!='1':pytest.skip('真实模型未显式启用')
 c,s,uid,_,app=notes;seed(s,uid);seed(s,uid,2);settings=load_settings();engine=create_engine(postgres_url(settings.database_url.get_secret_value()),hide_parameters=True)
 with Session(engine) as db:
  config=db.scalar(select(AIConfig).where(AIConfig.enabled.is_(True),AIConfig.is_default.is_(True),AIConfig.deleted_at.is_(None)));assert config
  values={k:getattr(config,k) for k in ('base_url','model_id','protocol','encrypted_key','key_version','key_mask')}
 engine.dispose()
 with s.begin() as db:db.add(AIConfig(user_id=uid,create_request_id=uuid4(),create_fingerprint='synthetic',name='attractor-synthetic',is_default=True,**values))
 app.state.settings=settings;monkeypatch.undo();r=c.post('/api/life-os/attractors/analyze',headers=H,json=payload());assert r.status_code==200,r.text
 assert r.json()['status']=='succeeded';print('LIVE_ATTRACTOR_USAGE',r.json()['usage'])
 assert c.post('/api/life-os/attractors/read',headers=H,json=payload()).json()['current']['id']==r.json()['id']

def test_attractor_browser(notes,monkeypatch):
 import socket,threading,time,uvicorn
 from playwright.sync_api import sync_playwright,expect
 c,s,uid,_,app=notes;seed(s,uid)
 def model(self,user,purpose,messages,request_id,**kw):return {'content':response_for(json.loads(messages[1]['content'])['events']),'usage':None}
 monkeypatch.setattr(AIService,'generate',model)
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False));thread=threading.Thread(target=server.run,daemon=True);thread.start()
 try:
  for _ in range(100):
   if server.started:break
   time.sleep(.05)
  with sync_playwright() as pw:
   browser=pw.chromium.launch(channel='msedge',headless=True);page=browser.new_page(viewport={'width':1366,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.context.add_cookies([{'name':'camp_session','value':str(uid),'url':f'http://127.0.0.1:{port}'}]);page.goto(f'http://127.0.0.1:{port}/life-os')
   area=page.locator('#life-attractors');area.locator('input[type=checkbox]').check();area.get_by_role('button',name='分析所选时间周期').click();dot=area.locator('svg circle[role=button]');expect(dot).to_have_count(1,timeout=30000);dot.click();expect(area).to_contain_text('合成恢复事件');area.get_by_text('完整原始记录',exact=False).click();expect(area).to_contain_text('合成事件：学习受挫时');page.reload();expect(dot).to_have_count(1,timeout=30000);page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors,errors;browser.close()
 finally:server.should_exit=True;thread.join(10)

def test_invalid_sources_and_missing_evidence_rejected():
 from app.modules.life_os.attractors import validate
 eid,sid=str(uuid4()),str(uuid4());events=[{'id':eid,'sources':[{'id':sid,'text':'真实依据'}],'occurred_at':datetime.now(timezone.utc).isoformat()}]
 out=Output(patterns=[{'name':'观察','description':'待验证','mechanism':'','intervention':'','links':[{'event_id':eid,'source_id':sid,'quote':'编造引文','strength':'unknown','reason':'合成'}]}],current_pattern=None,current_event_id=None,insufficient_reason='')
 with pytest.raises(AIError):validate(out,{'events':events})

def test_note_only_event_requires_explicit_authorization(notes,monkeypatch):
 from app.modules.distractions.models import DistractionNote
 c,s,uid,_,_=notes
 with s.begin() as db:
  n=DistractionNote(user_id=uid,create_request_id=uuid4(),create_fingerprint='synthetic',content='合成杂念：先听音乐再整理桌面');db.add(n);db.flush()
  e=LifeEvent(user_id=uid,title='杂念来源事件',occurred_at=datetime.now(timezone.utc),status='confirmed',version=1);db.add(e);db.flush();db.add(EventSource(user_id=uid,event_id=e.id,note_id=n.id));nid=str(n.id)
 p=payload();url='/api/life-os/attractors/'
 r=c.post(url+'analyze',headers=H,json=p);assert r.status_code==200 and r.json()['result']['patterns']==[]
 def model(self,user,purpose,messages,request_id,**kw):return {'content':response_for(json.loads(messages[1]['content'])['events']),'usage':None}
 monkeypatch.setattr(AIService,'generate',model)
 p['note_ids']=[nid];r=c.post(url+'analyze',headers=H,json=p);assert r.status_code==200,r.text
 assert c.post(url+'read',headers=H,json=payload()).json()['current']['result']['patterns']==[]
 with s.begin() as db:db.get(DistractionNote,UUID(nid)).deleted_at=datetime.now(timezone.utc)
 assert c.post(url+'read',headers=H,json=p).status_code==409
 assert c.post(url+'analyze',headers=H,json=p|{'start':p['end'],'end':'2000-01-01'}).status_code==422

def test_old_map_keeps_evidence_but_clears_outdated_position():
 from app.modules.life_os.attractors import validate
 old,new,sid=str(uuid4()),str(uuid4()),str(uuid4())
 context={'events':[{'id':new,'occurred_at':datetime.now(timezone.utc).isoformat(),'sources':[]},{'id':old,'occurred_at':datetime.now(timezone.utc).isoformat(),'sources':[{'id':sid,'text':'有效引句'}]}]}
 out=Output(patterns=[{'name':'观察','description':'观察','mechanism':'','intervention':'','links':[{'event_id':old,'source_id':sid,'quote':'有效引句','strength':'unknown','reason':'观察'}]}],current_pattern=0,current_event_id=old,insufficient_reason='')
 with pytest.raises(AIError):validate(out.model_copy(deep=True),context)
 assert validate(out,context,strict_current=False)['current_pattern'] is None
