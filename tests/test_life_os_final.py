"""Cross-module browser acceptance with real isolated PostgreSQL."""
import json,socket,threading,time
from uuid import UUID
from datetime import datetime
from zoneinfo import ZoneInfo
import uvicorn
from playwright.sync_api import sync_playwright,expect
from app.modules.ai_gateway.service import AIService
from app.modules.life_os.schedule import ScheduleOutput
from app.modules.life_os.attractors import Output as MapOutput
from test_life_os_problems_postgres import make_output
from test_distractions_postgres import notes
from test_tasks_postgres import task_engine
H={'Origin':'http://testserver'}
def test_whole_page_authorized_flow_and_serial_model_calls(notes,monkeypatch):
 c,_,uid,_,app=notes;active=0;maximum=0;calls=[];guard=threading.Lock()
 def model(self,user,purpose,messages,request_id,**kw):
  nonlocal active,maximum
  with guard:active+=1;maximum=max(maximum,active)
  try:
   time.sleep(.25);ctx=json.loads(messages[1]['content']);calls.append(purpose)
   if purpose=='life_os_core':
    m=ctx['recent_messages'][-1];out=make_output(m['id'],m['content'],ctx['problem_context'],'continue' if ctx['problem_context']['events'] else 'new')
    assert ctx['restart_protocol'] and ctx['restart_protocol'][0]['title']=='恢复环境'
   elif purpose=='life_os_schedule':out=ScheduleOutput(reason='合成联调：保留固定事务，降低其他负荷',daily=[],weekly=[],today_summary='轻量恢复')
   else:
    e=ctx['events'][0];source=e['sources'][0]
    out=MapOutput(patterns=[{'name':'合成恢复观察','description':'来自真实测试事件','mechanism':'暂待验证','intervention':'从小动作开始','links':[{'event_id':e['id'],'source_id':source['id'],'quote':source['text'][:20],'strength':'unknown','reason':'本轮原文依据'}]}],current_pattern=None,current_event_id=None,insufficient_reason='')
   return {'content':out,'usage':None,'model_id':'controlled-final','config_version':1}
  finally:
   with guard:active-=1
 monkeypatch.setattr(AIService,'generate',model)
 assert c.post('/api/life-os/scenes',headers=H,json={'name':'验收场景','daily_slots':[{'start':'23:50','end':'23:59','activity':'固定生活事务','fixed':True}],'weekly_rhythm':[]}).status_code==200
 c.post('/api/life-os/mode',headers=H,json={'mode':'blue'})
 c.post('/api/life-os/care/save',headers=H,json={'version':0,'items':['喝水'],'stages':[{'title':'恢复环境','items':['整理一个角落']}]})
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False));thread=threading.Thread(target=server.run,daemon=True);thread.start()
 try:
  for _ in range(100):
   if server.started:break
   time.sleep(.05)
  with sync_playwright() as pw:
   browser=pw.chromium.launch(channel='msedge',headless=True);page=browser.new_page(viewport={'width':1366,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.context.add_cookies([{'name':'camp_session','value':str(uid),'url':f'http://127.0.0.1:{port}'}]);page.goto(f'http://127.0.0.1:{port}/life-os')
   page.locator('#life-schedule-consent').check();page.locator('#life-attractors input[type=checkbox]').check();page.locator('#life-os-consent').check()
   page.locator('#life-os-input').fill('合成验收：又被拒了，感觉自己学的东西没啥用，今天本来安排了很多事情，但是现在什么都不想做，房间也乱得不行。');page.locator('#life-os-send').click()
   expect(page.locator('#life-os-feedback')).to_have_text('分析已保存。',timeout=30000)
   expect(page.locator('#life-schedule-daily')).to_contain_text('合成联调',timeout=45000)
   expect(page.locator('#life-attractors svg circle[role=button]')).to_have_count(1,timeout=45000)
   expect(page.locator('#life-mode-summary')).to_contain_text('当前由你手动选择')
   expect(page.locator('#life-mode-list button[data-mode=blue]')).to_have_attribute('aria-pressed','true')
   expect(page.locator('#life-layers li.is-highlighted')).to_have_count(1)
   expect(page.locator('#life-problem-list tbody tr td').first).to_have_text('1')
   page.locator('#life-care input[type=checkbox]').check();expect(page.locator('#life-care')).to_contain_text('100%')
   page.locator('#life-attractors svg circle[role=button]').click();expect(page.locator('#life-attractors')).to_contain_text('合成验收：又被拒了')
   page.get_by_role('button',name='编辑场景',exact=True).click()
   page.clock.install();editor=page.locator('.life-os-scene-editor input[name=name]').first;editor.fill('尚未保存的编辑');page.clock.fast_forward(61000);expect(editor).to_have_value('尚未保存的编辑')
   page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors,errors
   browser.close()
 finally:server.should_exit=True;thread.join(10)
 assert maximum==1 and {'life_os_core','life_os_schedule','life_os_attractors'}<=set(calls)
 assert c.get('/api/life-os/scenes').json()['items'][0]['name']=='验收场景'


def test_synthetic_module_restore_roundtrip(notes,monkeypatch):
 from sqlalchemy import MetaData,Table,select,text,create_engine,inspect
 from alembic import command
 from alembic.config import Config
 from app.core.config import ROOT,postgres_url
 import os
 from uuid import uuid4
 from cryptography.fernet import Fernet
 c,s,uid,_,app=notes
 c.post('/api/life-os/care/save',headers=H,json={'version':0,'items':['恢复测试事项'],'stages':[{'title':'恢复阶段','items':['测试动作']}]})
 care=c.get('/api/life-os/care').json();c.post('/api/life-os/care/check',headers=H,json={'day':care['today'],'item_id':care['record']['items'][0]['id'],'checked':True})
 c.post('/api/life-os/scenes',headers=H,json={'name':'恢复场景','daily_slots':[],'weekly_rhythm':[]})
 c.post('/api/life-os/mode',headers=H,json={'mode':'blue'})
 m=c.post('/api/life-os/messages',headers=H,json={'request_id':str(uuid4()),'content':'合成恢复原文：今天桌面很乱。'}).json()
 def generate(self,user,purpose,messages,request_id,**kw):
  ctx=json.loads(messages[1]['content'])
  if purpose=='life_os_core':
   msg=ctx['recent_messages'][-1];out=make_output(msg['id'],msg['content'],ctx['problem_context'])
  elif purpose=='life_os_schedule':out=ScheduleOutput(reason='恢复测试',daily=[],weekly=[],today_summary='暂无安排')
  else:out=MapOutput(patterns=[],current_pattern=None,current_event_id=None,insufficient_reason='合成资料待积累')
  return {'content':out,'model_id':'restore-synthetic','config_version':1,'usage':None}
 monkeypatch.setattr(AIService,'generate',generate)
 assert c.post('/api/life-os/messages/'+m['id']+'/analyze',headers=H,json={'request_id':str(uuid4()),'consent_external':True}).status_code==200
 assert c.post('/api/life-os/layers/experiences',headers=H,json={'model':'life','layer':'生活秩序','occurred_on':care['today'],'event':'合成恢复事件','experience':'合成经验'}).status_code==200
 assert c.post('/api/life-os/schedule/generate',headers=H,json={'consent_external':True}).status_code==200
 assert c.post('/api/life-os/attractors/analyze',headers=H,json={'start':care['today'],'end':care['today'],'consent_external':True}).status_code==200
 schema='ac_life_restore_'+uuid4().hex;url=postgres_url(os.environ['TEST_DATABASE_URL']);admin=create_engine(url,hide_parameters=True,connect_args={'connect_timeout':5});engine=create_engine(url,hide_parameters=True,connect_args={'connect_timeout':5,'options':f'-c search_path={schema} -c statement_timeout=30000'})
 try:
  with admin.begin() as db:db.execute(text(f'CREATE SCHEMA "{schema}"'))
  with engine.begin() as db:
   cfg=Config(str(ROOT/'alembic.ini'));cfg.attributes['connection']=db;command.upgrade(cfg,'head');command.check(cfg)
  with s() as source:
   inspector=inspect(source.bind);selected={'users'}|{name for name in inspector.get_table_names() if name.startswith('life_os_')}
   dependencies={name:{fk['referred_table'] for fk in inspector.get_foreign_keys(name) if fk['referred_table'] in selected and fk['referred_table']!=name} for name in selected}
   names=[]
   while dependencies:
    ready=sorted(name for name,deps in dependencies.items() if not deps)
    assert ready,'unexpected circular dependencies in isolated Life OS restore'
    names.extend(ready)
    for name in ready:dependencies.pop(name)
    for deps in dependencies.values():deps.difference_update(ready)
   snapshot={}
   for name in names:
    table=Table(name,MetaData(),autoload_with=source.bind);predicate=table.c.id==uid if name=='users' else table.c.user_id==uid
    snapshot[name]=[dict(row) for row in source.execute(select(table).where(predicate)).mappings()]
  # This synthetic encrypted archive exercises serialization, not a production backup.
  from datetime import date
  def encode(v):
   if isinstance(v,UUID):return {'$uuid':str(v)}
   if isinstance(v,datetime):return {'$datetime':v.isoformat()}
   if isinstance(v,date):return {'$date':v.isoformat()}
   raise TypeError(type(v).__name__)
  def decode(v):
   if set(v)=={'$uuid'}:return UUID(v['$uuid'])
   if set(v)=={'$datetime'}:return datetime.fromisoformat(v['$datetime'])
   if set(v)=={'$date'}:return date.fromisoformat(v['$date'])
   return v
  cipher=Fernet(Fernet.generate_key());archive=cipher.encrypt(json.dumps(snapshot,default=encode,sort_keys=True).encode());restored=json.loads(cipher.decrypt(archive),object_hook=decode)
  with engine.begin() as db:
   for name in names:
    table=Table(name,MetaData(),autoload_with=db)
    if restored[name]:db.execute(table.insert(),restored[name])
   for name in names:
    table=Table(name,MetaData(),autoload_with=db);actual=[dict(row) for row in db.execute(select(table)).mappings()]
    canon=lambda rows:sorted(json.dumps(r,sort_keys=True,default=str) for r in rows)
    assert canon(actual)==canon(snapshot[name]),name
  print('RESTORE_SYNTHETIC_TABLES',len(names),'ROWS',sum(map(len,snapshot.values())))
 finally:
  engine.dispose()
  with admin.begin() as db:db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
  admin.dispose()
