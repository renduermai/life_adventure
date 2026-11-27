from uuid import uuid4
from datetime import timedelta
from app.modules.life_os import care
from test_distractions_postgres import notes
from test_tasks_postgres import task_engine
H={'Origin':'http://testserver'}
def test_care_days_progress_history_and_permissions(notes):
 c,s,uid,other,app=notes
 initial=c.get('/api/life-os/care').json();assert initial['progress']['percent'] is None
 config={'version':0,'items':['吃饭','喝水','睡觉','洗漱'],'stages':[{'title':'恢复环境','items':['整理桌面']}]}
 r=c.post('/api/life-os/care/save',headers=H,json=config);assert r.status_code==200,r.text
 d=r.json();day=d['today'];ids=[x['id'] for x in d['record']['items']]
 for i in ids:
  r=c.post('/api/life-os/care/check',headers=H,json={'day':day,'item_id':i,'checked':True});assert r.status_code==200,r.text
 assert r.json()['progress']['percent']==100 and len(r.json()['record']['successes'])==3
 c.post('/api/life-os/care/check',headers=H,json={'day':day,'item_id':ids[-1],'checked':False})
 r=c.post('/api/life-os/care/check',headers=H,json={'day':day,'item_id':ids[-1],'checked':True});assert len(r.json()['record']['successes'])==3
 assert c.post('/api/life-os/care/save',headers=H,json=config).status_code==409
 c.cookies.set('camp_session',str(other));assert c.get('/api/life-os/care').json()['version']==0
 assert c.post('/api/life-os/care/check',headers=H,json={'day':day,'item_id':ids[0],'checked':True}).status_code==404
 c.cookies.set('camp_session',str(uid))
 from datetime import date
 tomorrow=str(date.fromisoformat(day)+timedelta(days=1));assert c.get('/api/life-os/care?day='+tomorrow).json()['progress']['done']==0
 assert c.get('/api/life-os/care').json()['progress']['done']==4

def test_care_browser(notes):
 import socket,threading,time,uvicorn
 from playwright.sync_api import sync_playwright,expect
 c,_,uid,_,app=notes
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False));thread=threading.Thread(target=server.run,daemon=True);thread.start()
 try:
  for _ in range(100):
   if server.started:break
   time.sleep(.05)
  with sync_playwright() as pw:
   browser=pw.chromium.launch(channel='msedge',headless=True);page=browser.new_page(viewport={'width':390,'height':844});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.context.add_cookies([{'name':'camp_session','value':str(uid),'url':f'http://127.0.0.1:{port}'}]);page.goto(f'http://127.0.0.1:{port}/life-os')
   area=page.locator('#life-care');area.get_by_text('编辑保障清单与恢复阶段',exact=True).click()
   area.locator('form > textarea').fill('喝水')
   area.get_by_role('button',name='保存清单与协议').click();expect(area.locator('input[type=checkbox]')).to_have_count(1);expect(area).to_contain_text('喝水')
   area.locator('input[type=checkbox]').check();expect(area).to_contain_text('100%')
   page.reload();expect(area).to_contain_text('100%');assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors,errors;browser.close()
 finally:server.should_exit=True;thread.join(10)
