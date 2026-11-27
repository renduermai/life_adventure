import json,socket,threading,time,tempfile
from pathlib import Path
from uuid import UUID
import uvicorn
from playwright.sync_api import sync_playwright,expect
from app.modules.ai_gateway.service import AIService
from test_distractions_postgres import notes
from test_tasks_postgres import task_engine
from test_life_os_problems_postgres import make_output

def test_problem_library_ui_with_real_postgres(notes,monkeypatch):
    client,_,uid,_,app=notes
    def generate(self,user,purpose,messages,request_id,**kw):
        data=json.loads(messages[1]['content']);m=data['recent_messages'][-1];ctx=data['problem_context']
        result=make_output(m['id'],m['content'],ctx,'continue' if ctx['events'] else 'new')
        return {'content':result,'model_id':'mock','config_version':1,'usage':None}
    monkeypatch.setattr(AIService,'generate',generate)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False));thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.context.add_cookies([{'name':'camp_session','value':str(uid),'url':f'http://127.0.0.1:{port}'}])
            page.goto(f'http://127.0.0.1:{port}/life-os')
            def chat(text):
                page.locator('#life-os-input').fill(text);page.locator('#life-os-consent').check();page.locator('#life-os-send').click();expect(page.locator('#life-os-feedback')).to_have_text('分析已保存。',timeout=30000)
            chat('今天桌面很乱。')
            table=page.locator('#life-problem-list');expect(table.locator('tbody tr')).to_have_count(1);expect(table.locator('tbody tr td').first).to_have_text('1')
            table.get_by_role('button',name='环境混乱',exact=True).click()
            d=page.locator('#life-problem-detail');d.get_by_text('管理问题',exact=True).click()
            d.locator('textarea[name=mechanism]').fill('我的手动处理方式');d.get_by_role('button',name='保存问题',exact=True).click()
            expect(page.locator('#life-problem-feedback')).to_have_text('问题已保存，手动内容已保护。')
            chat('继续刚才同一次事件，我仍然在整理这张桌子。')
            expect(table.locator('tbody tr td').first).to_have_text('1');expect(table).to_contain_text('我的手动处理方式')
            table.get_by_role('button',name='环境混乱',exact=True).click()
            card=d.locator('.life-event-card').first;card.locator(':scope > summary').click()
            card.locator('textarea[name=action]').fill('移走了杯子');card.locator('textarea[name=feedback]').fill('感觉舒服一些');card.locator('select[name=outcome]').select_option('helpful');card.get_by_role('button',name='保存实际反馈',exact=True).click()
            expect(page.locator('#life-problem-feedback')).to_have_text('实际反馈已保存。',timeout=15000)
            card=d.locator('.life-event-card').first;card.locator(':scope > summary').click();expect(card).to_contain_text('反馈有效',timeout=15000)
            page.reload();expect(table).to_contain_text('我的手动处理方式');expect(table.locator('tbody tr td').first).to_have_text('1')
            page.set_viewport_size({'width':390,'height':844});expect(page.locator('#sidebar')).to_have_css('visibility','hidden')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            output=Path(tempfile.gettempdir())/'life-os-step3';output.mkdir(exist_ok=True);page.screenshot(path=str(output/'mobile.png'),full_page=True)
            assert not errors,errors
            browser.close()
    finally:server.should_exit=True;thread.join(10)
