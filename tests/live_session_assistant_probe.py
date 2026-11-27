"""Explicit --live V3 assistant probe, synthetic account/target, real AI/DB/browser."""
import secrets
import json
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright,expect
from sqlalchemy import delete,func,select
from app.main import create_app
from app.core.config import Settings
from app.modules.identity.models import User,LoginSession
from app.modules.identity.service import token_hash
from app.modules.ai_gateway.models import AIConfig,AICallLog
from app.modules.tasks.models import Task
from app.modules.quests.models import MainQuest
from app.modules.startup_chat.models import ChatTurn,Conversation
from app.modules.startup_chat.breakdown_models import BreakdownPlan
from app.modules.startup_items.models import StartupItem


def run():
    assert '--live' in sys.argv
    from app.modules.ai_gateway import service as gateway
    original=gateway.post_json
    def diagnostic(*args,**kwargs):
        value=original(*args,**kwargs)
        content=value.get('choices',[{}])[0].get('message',{}).get('content','')
        if isinstance(content,str) and 'response_format' in args[2]:
            try:json.loads(content)
            except json.JSONDecodeError as exc:
                window=content[max(0,exc.pos-20):exc.pos+20]
                masked=re.sub(r'[^\s{}\[\]:,\"`\\]','?',window)
                print('SYNTHETIC_JSON_DIAG',{'length':len(content),'fenced':content.strip().startswith('```'),'error':exc.msg,'offset':exc.pos,'syntax':masked},flush=True)
        return value
    gateway.post_json=diagnostic
    app=create_app(Settings(log_level='ERROR'));database=app.state.database
    uid,qid,tid=uuid4(),uuid4(),uuid4();token=secrets.token_urlsafe(32);server=None;thread=None
    try:
        with database.transaction() as db:
            config=db.scalar(select(AIConfig).where(AIConfig.is_default.is_(True),AIConfig.deleted_at.is_(None),AIConfig.enabled.is_(True)))
            assert config
            db.add(User(id=uid,username='session_probe_'+uid.hex,password_hash='unused-test-only',display_name='合成会话验收',timezone='Asia/Shanghai'));db.flush()
            db.add(LoginSession(user_id=uid,token_hash=token_hash(token),expires_at=datetime.now(timezone.utc)+timedelta(hours=1)))
            db.add(AIConfig(user_id=uid,name='合成验收模型',base_url=config.base_url,model_id=config.model_id,encrypted_key=config.encrypted_key,key_version=config.key_version,key_mask='已设置',create_request_id=uuid4(),create_fingerprint='x'*64,enabled=True,is_default=True))
            db.add(MainQuest(id=qid,user_id=uid,title='合成：整理开发资料',description='希望更容易找到开发文件',manual_focus_status='routine_practice'));db.flush()
            db.add(Task(id=tid,user_id=uid,main_quest_id=qid,title='合成：整理项目文件夹',description='最终希望把测试文件分门别类，目前已经建好目录，文件尚未移动。',manual_focus_status='routine_practice'))
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8774,log_level='error',access_log=False));thread=threading.Thread(target=server.run,daemon=True);thread.start()
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True);context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
            context.add_cookies([{'name':'camp_session','value':token,'url':'http://127.0.0.1:8774'}]);page=context.new_page()
            page.goto('http://127.0.0.1:8774/startup');expect(page.locator('#chat-input')).to_be_enabled(timeout=20000)
            def send(message):
                page.locator('#chat-input').fill(message);page.locator('#chat-form button').click();expect(page.locator('#chat-input')).to_be_enabled(timeout=120000)
            send('合成测试：我今天有点焦虑，想先聊聊，不急着规划任务。')
            expect(page.locator('.chat-answer')).to_have_count(1)
            page.reload();expect(page.locator('.chat-answer')).to_have_count(1,timeout=20000)
            page.goto('http://127.0.0.1:8774/tasks/'+str(tid));page.locator('[data-breakdown-link]').click()
            expect(page.locator('#chat-target')).to_contain_text('合成：整理项目文件夹',timeout=20000)
            expect(page.locator('.chat-answer')).to_have_count(1,timeout=120000)
            expect(page.locator('#chat-input')).to_be_enabled(timeout=120000)
            send('最终想整理测试文件，目前目录已建好，今天只做十分钟；我最大的困难是不知道先碰哪个文件，请给可以开始的小步骤。')
            expect(page.locator('.chat-answer')).to_have_count(2)
            expect(page.get_by_role('button',name='复制步骤',exact=True).last).to_be_visible()
            send('第一步还是太难，我只剩一分钟。请只给我一个极小动作，不需要整理完整个目录。')
            expect(page.locator('.chat-answer')).to_have_count(3)
            stored=page.evaluate("JSON.parse(sessionStorage.getItem('adventure-assistant-v3'))")
            assert stored['turns'][-1]['response']['minimum_action']
            assert len(stored['turns'][-1]['response']['steps'])==1
            assert sum(step['minutes'] for step in stored['turns'][-1]['response']['steps'])<=1
            page.reload();expect(page.locator('.chat-answer')).to_have_count(3,timeout=20000)
            with database.transaction() as db:
                logs=list(db.scalars(select(AICallLog).where(AICallLog.user_id==uid)))
                print('LIVE_SESSION_CALLS',[(r.status,r.error_code,r.usage) for r in logs],flush=True)
                assert len(logs)==4 and all(r.status=='succeeded' for r in logs)
                for model in (ChatTurn,Conversation,BreakdownPlan,StartupItem):
                    assert db.scalar(select(func.count()).select_from(model).where(model.user_id==uid))==0
                task=db.get(Task,tid);quest=db.get(MainQuest,qid)
                assert task.manual_focus_status==quest.manual_focus_status=='routine_practice'
                assert task.status=='todo' and task.version==1 and quest.status=='active'
            page.once('dialog',lambda dialog:dialog.accept());page.locator('#chat-new').click();expect(page.locator('.chat-answer')).to_have_count(0)
            page.set_viewport_size({'width':390,'height':844});expect(page.locator('#sidebar')).to_be_hidden();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            browser.close()
        print('LIVE_PASS free + task entry + goal/progress + feedback shrink + reload no AI + reset + no formal writes + 390px',flush=True)
    except Exception:
        with database.transaction() as db:
            print('LIVE_FAILED_CALLS',[(r.purpose,r.status,r.error_code,r.elapsed_ms,r.usage) for r in db.scalars(select(AICallLog).where(AICallLog.user_id==uid))],flush=True)
        raise
    finally:
        gateway.post_json=original
        if server:server.should_exit=True
        if thread:thread.join(10)
        with database.transaction() as db:
            for model in (AICallLog,AIConfig,Task,MainQuest,LoginSession):db.execute(delete(model).where(model.user_id==uid))
            db.execute(delete(User).where(User.id==uid))
        database.dispose()


if __name__=='__main__':run()
