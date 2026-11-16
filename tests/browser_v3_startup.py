"""V3 layout/autosave browser checks with synthetic HTTP, no AI or DB writes."""
import sys,threading,time,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright,expect
from app.main import create_app
from app.core.config import Settings

def run():
 app=create_app(Settings(_env_file=None,log_level='ERROR'))
 server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8768,log_level='error',access_log=False))
 thread=threading.Thread(target=server.run,daemon=True);thread.start()
 saved={'generation':0,'state':None};writes=[];calls=[];fail=False
 def respond(route):
  nonlocal saved,fail
  path=route.request.url.split('8768')[1].split('?')[0];calls.append(path)
  if path=='/api/startup/current':value=saved
  elif path=='/api/startup/states':
   data=route.request.post_data_json;writes.append(data)
   if fail:route.fulfill(status=503,json={'error':'Synthetic offline'});return
   assert data['expected_generation']==saved['generation']
   saved=dict(data,generation=saved['generation']+1,snapshot_id='00000000-0000-0000-0000-000000000001')
   value=saved
  elif path=='/api/startup/items':value={'items':[],'next_offset':None}
  elif path=='/api/startup/chat/conversations':value={'items':[],'next_offset':None}
  else:raise AssertionError(path)
  route.fulfill(json=value)
 try:
  for _ in range(100):
   if server.started:break
   time.sleep(.05)
  with sync_playwright() as pw:
   browser=pw.chromium.launch(channel='msedge',headless=True)
   page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
   page.on('pageerror',lambda error:errors.append(str(error)));page.route('**/api/**',respond)
   page.goto('http://127.0.0.1:8768/startup');expect(page.locator('#pressure')).to_be_enabled()
   def move(p,e):
    page.evaluate('([p,e])=>{for(const [id,value] of [["pressure",p],["energy",e]]){const n=document.getElementById(id);n.value=value;n.dispatchEvent(new Event("input",{bubbles:true}));}}',[p,e])
   for p,e,index in [(80,20,3),(20,80,0),(80,80,1),(20,20,2),(0,100,0),(100,0,3)]:
    move(p,e);expect(page.locator('#state-dot')).to_have_attribute('cx',str(p));expect(page.locator('#state-dot')).to_have_attribute('cy',str(100-e));expect(page.locator('.quadrant').nth(index)).to_have_class(__import__('re').compile('is-current'))
   move(80,25);expect(page.locator('#state-message')).to_have_text('已自动保存')
   assert saved['pressure']==80 and saved['energy']==25
   page.reload();expect(page.locator('#pressure')).to_have_value('80');expect(page.locator('#energy')).to_have_value('25')
   fail=True;move(30,70);expect(page.locator('#state-retry')).to_be_visible();expect(page.locator('#pressure')).to_have_value('30')
   request_id=writes[-1]['request_id'];fail=False;page.locator('#state-retry').click();expect(page.locator('#state-message')).to_have_text('已自动保存');assert writes[-1]['request_id']==request_id
   assert not any('/recommendations' in p or '/refresh' in p for p in calls)
   assert not page.locator('#task-scatter a').count()
   assert not page.locator('#state-form').count()
   expect(page.locator('#chat-input')).to_be_enabled()
   out=Path(tempfile.gettempdir())/'adventure-v3-step3';out.mkdir(exist_ok=True)
   page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(out/'desktop.png'),full_page=True)
   page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   page.screenshot(path=str(out/'mobile.png'),full_page=True)
   assert not errors,errors
   browser.close();print('PASS V3 coordinates/boundaries/highlight/debounce/autosave/reload/failure/idempotent retry/no AI/390px')
 finally:server.should_exit=True;thread.join(10)
if __name__=='__main__':run()
