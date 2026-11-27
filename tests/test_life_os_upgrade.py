"""Acceptance for 20 rounds, note fallback, layer points and revised page."""
import json,socket,threading,time
from uuid import UUID,uuid4
from datetime import datetime,timezone
import pytest,uvicorn
from playwright.sync_api import sync_playwright,expect
from app.modules.ai_gateway.service import AIService
from app.modules.life_os.models import Message,Analysis
from test_life_os_postgres import output
from test_life_os_problems_postgres import make_output
from test_distractions_postgres import notes
from test_tasks_postgres import task_engine
H={'Origin':'http://testserver'}
def test_all_notes_blank_input_and_twenty_rounds(notes,monkeypatch):
 c,s,uid,other,app=notes;ids=[];raw=[]
 for i in range(4):
  text='合成杂念'+str(i)+'：'+'字'*1600;raw.append(text)
  r=c.post('/api/distractions/notes',headers=H,json={'request_id':str(uuid4()),'content':text});assert r.status_code==200;ids.append(r.json()['id'])
 saved=c.post('/api/life-os/messages',headers=H,json={'request_id':str(uuid4()),'content':'','note_ids':ids});assert saved.status_code==200,saved.text
 assert saved.json()['content']=='\n\n'.join(raw) and len(saved.json()['content'])>4000
 seen=[]
 def model(self,user,purpose,messages,request_id,**kw):
  ctx=json.loads(messages[1]['content']);seen.append(ctx);m=ctx['recent_messages'][-1];return {'content':make_output(m['id'],m['content'],ctx['problem_context']),'model_id':'synthetic','config_version':1,'usage':None}
 monkeypatch.setattr(AIService,'generate',model)
 result=c.post('/api/life-os/messages/'+saved.json()['id']+'/analyze',headers=H,json={'request_id':str(uuid4()),'consent_external':True,'note_ids':ids});assert result.status_code==200,result.text
 assert len(seen[-1]['problem_context']['selected_notes'])==4 and result.json()['result']['event'] is None
 assert c.post('/api/life-os/messages/'+saved.json()['id']+'/analyze',headers=H,json={'request_id':str(uuid4()),'consent_external':True,'note_ids':[]}).status_code==422
 with s.begin() as db:
  for i in range(25):db.add(Message(user_id=uid,request_id=uuid4(),content='合成上下文第'+str(i)+'轮'))
 last=c.post('/api/life-os/messages',headers=H,json={'request_id':str(uuid4()),'content':'合成当前问题：桌面乱'}).json()
 r=c.post('/api/life-os/messages/'+last['id']+'/analyze',headers=H,json={'request_id':str(uuid4()),'consent_external':True});assert r.status_code==200,r.text
 assert len(seen[-1]['recent_messages'])==20
 assert saved.json()['id'] not in {m['id'] for m in seen[-1]['recent_messages']}
 assert len(c.get('/api/life-os/layer-points?rounds=1').json()['items'])==1
 assert c.get('/api/life-os/layer-points?rounds=3').status_code==422
 c.cookies.set('camp_session',str(other));assert c.get('/api/life-os/layer-points?rounds=30').json()['items']==[]
 assert c.post('/api/life-os/messages',headers=H,json={'request_id':str(uuid4()),'note_ids':ids}).status_code==404
 # The shared fixture also checks downgrading the old 4000-character schema; only this disposable synthetic long row is shortened after all feature assertions.
 with s.begin() as db:db.get(Message,UUID(saved.json()['id'])).content='合成长输入测试已验证，清理旧版迁移测试数据'

def test_upgraded_page_browser(notes,monkeypatch):
 c,s,uid,_,app=notes
 for i in range(4):c.post('/api/distractions/notes',headers=H,json={'request_id':str(uuid4()),'content':'合成待分析杂念'+str(i)})
 with s.begin() as db:
  for i in range(30):
   m=Message(user_id=uid,request_id=uuid4(),content='合成第'+str(i)+'轮');db.add(m);db.flush();db.add(Analysis(user_id=uid,message_id=m.id,request_id=uuid4(),status='succeeded',result=output(m.id).model_dump(mode='json'),source_ids=[str(m.id)],prompt_version='synthetic',finished_at=datetime.now(timezone.utc)))
 def model(self,user,purpose,messages,request_id,**kw):
  ctx=json.loads(messages[1]['content']);m=ctx['recent_messages'][-1];return {'content':make_output(m['id'],m['content'],ctx['problem_context']),'model_id':'mock','config_version':1,'usage':None}
 monkeypatch.setattr(AIService,'generate',model)
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False));thread=threading.Thread(target=server.run,daemon=True);thread.start()
 try:
  for _ in range(100):
   if server.started:break
   time.sleep(.05)
  with sync_playwright() as pw:
   browser=pw.chromium.launch(channel='msedge',headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.context.add_cookies([{'name':'camp_session','value':str(uid),'url':f'http://127.0.0.1:{port}'}]);page.goto(f'http://127.0.0.1:{port}/life-os')
   expect(page.locator('#life-os-top-timeline')).to_contain_text('下一个锚点',timeout=20000)
   expect(page.locator('#life-weekly-schedule')).to_contain_text('AI学习 + 投递')
   expect(page.locator('#life-care input[type=checkbox]')).to_have_count(6,timeout=20000)
   page.locator('#life-care input[type=checkbox]').first.check();expect(page.locator('#life-care')).to_contain_text('1/6',timeout=20000)
   assert c.get('/api/life-os/care').json()['version']==1
   expect(page.locator('#life-layers .life-layer-dot')).to_have_count(30,timeout=30000)
   page.locator('#life-layer-rounds').select_option('5');expect(page.locator('#life-layers .life-layer-dot')).to_have_count(5,timeout=30000)
   page.get_by_role('button',name='＋ 新建场景').click();editor=page.locator('.life-os-scene-editor').last;editor.locator('input[name=name]').fill('新增测试场景');editor.get_by_role('button',name='保存场景',exact=True).click();expect(page.locator('.life-os-scene-editor')).to_have_count(0,timeout=20000)
   expect(page.get_by_role('button',name='版本历史',exact=True)).to_have_count(0)
   page.locator('.life-note-options > summary').click();page.locator('#life-note-select-all').click();expect(page.locator('.life-note-select:checked')).to_have_count(4,timeout=20000)
   page.locator('#life-os-consent').check();page.locator('#life-os-input').fill('');page.locator('#life-os-send').click();expect(page.locator('#life-os-feedback')).to_have_text('分析已保存。',timeout=30000)
   expect(page.locator('#life-attractors')).to_contain_text('默认参考图')
   from pathlib import Path
   import tempfile
   directory=Path(tempfile.gettempdir())/'life-os-upgrade';directory.mkdir(exist_ok=True);page.locator('.life-os-welcome').screenshot(path=str(directory/'top.png'));page.locator('#life-care').screenshot(path=str(directory/'care.png'));page.locator('#life-attractors').screenshot(path=str(directory/'attractors.png'))
   page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors,errors;browser.close()
 finally:server.should_exit=True;thread.join(10)

def test_live_selected_note_input(notes,monkeypatch):
 import os
 if os.getenv('LIFE_OS_LIVE')!='1':pytest.skip('真实模型未显式启用')
 from sqlalchemy import create_engine,select
 from sqlalchemy.orm import Session
 from app.core.config import load_settings,postgres_url
 from app.modules.ai_gateway.models import AIConfig
 c,s,uid,_,app=notes;settings=load_settings();engine=create_engine(postgres_url(settings.database_url.get_secret_value()),hide_parameters=True)
 with Session(engine) as db:
  config=db.scalar(select(AIConfig).where(AIConfig.enabled.is_(True),AIConfig.is_default.is_(True),AIConfig.deleted_at.is_(None)));assert config
  values={k:getattr(config,k) for k in ('base_url','model_id','protocol','encrypted_key','key_version','key_mask')}
 engine.dispose()
 with s.begin() as db:db.add(AIConfig(user_id=uid,create_request_id=uuid4(),create_fingerprint='synthetic',name='note-input-synthetic',is_default=True,**values))
 ids=[]
 for text in ['合成历史杂念：上周收到拒信很失落。','合成历史杂念：房间杂乱时更不想开始学习。','合成历史杂念：听音乐后整理桌面感觉轻松。','合成历史杂念：希望从一个很小的行动重新开始。']:
  n=c.post('/api/distractions/notes',headers=H,json={'request_id':str(uuid4()),'content':text});assert n.status_code==200;ids.append(n.json()['id'])
 saved=c.post('/api/life-os/messages',headers=H,json={'request_id':str(uuid4()),'content':'','note_ids':ids});assert saved.status_code==200
 app.state.settings=settings;monkeypatch.undo()
 result=c.post('/api/life-os/messages/'+saved.json()['id']+'/analyze',headers=H,json={'request_id':str(uuid4()),'consent_external':True,'note_ids':ids});assert result.status_code==200,result.text
 assert result.json()['result']['event'] is None and saved.json()['id'] in result.json()['result']['source_ids']
 print('LIVE_SELECTED_NOTES_USAGE',result.json()['usage'])
