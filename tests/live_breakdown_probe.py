"""Explicit, synthetic real-provider/DB/browser probe. Never collected by pytest.
Run with --live and optional PGHOSTADDR; uses a temporary account and cleans it.
"""
import os
import secrets
import sys
import tempfile
import threading
import time
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine,select,delete,func
from sqlalchemy.orm import sessionmaker
from playwright.sync_api import sync_playwright,expect
import uvicorn
from app.main import create_app
from app.core.config import Settings,postgres_url
from app.modules.identity.models import User,LoginSession
from app.modules.identity.service import token_hash
from app.modules.ai_gateway.models import AIConfig,AICallLog
from app.modules.startup_state.models import StateCurrent,StateSnapshot
from app.modules.startup_chat.breakdown_models import BreakdownPlan
from app.modules.tasks.models import Task,TaskCommand,TaskEvent
from app.modules.quests.models import MainQuest,QuestEvent
from app.modules.activity.models import FocusSession,FocusSegment,ActivityLog
from app.modules.task_recommendation.models import TaskAnalysis,RecommendationBatch


def run():
    assert '--live' in sys.argv,'Pass --live to authorize this synthetic provider probe'
    expect.set_options(timeout=60000)
    settings=Settings(log_level='ERROR');args={'connect_timeout':20,'options':'-c statement_timeout=20000'}
    if os.environ.get('PGHOSTADDR'):args['hostaddr']=os.environ['PGHOSTADDR']
    engine=create_engine(postgres_url(settings.database_url.get_secret_value()),hide_parameters=True,pool_size=5,max_overflow=3,connect_args=args)
    sessions=sessionmaker(engine,expire_on_commit=False)
    uid,qid,tid,snapshot_id=uuid4(),uuid4(),uuid4(),uuid4();token=secrets.token_urlsafe(32)
    from app.modules.ai_gateway import service as gateway
    from app.modules.startup_chat.breakdown_schemas import Advice
    from pydantic import ValidationError
    original_transport=gateway.post_json
    def diagnostic_transport(*args,**kwargs):
        value=original_transport(*args,**kwargs)
        try:Advice.model_validate_json(value['choices'][0]['message']['content'])
        except ValidationError as exc:print('MODEL_VALIDATION',exc.errors(include_input=False,include_url=False),value['choices'][0].get('finish_reason'),flush=True)
        return value
    gateway.post_json=diagnostic_transport
    created=False;server=None;thread=None;page=None
    out=Path(tempfile.gettempdir())/'adventure-step8-verification';out.mkdir(exist_ok=True)
    try:
        with sessions.begin() as db:
            config=db.scalar(select(AIConfig).where(AIConfig.is_default.is_(True),AIConfig.deleted_at.is_(None)))
            assert config,'No provider configured'
            db.add(User(id=uid,username='verify8_'+uid.hex,password_hash='unused-verification',display_name='拆解验收',timezone='Asia/Shanghai'));db.flush()
            db.add(LoginSession(user_id=uid,token_hash=token_hash(token),expires_at=datetime.now(timezone.utc)+timedelta(hours=1)))
            db.add(AIConfig(user_id=uid,name='验收模型',base_url=config.base_url,model_id=config.model_id,encrypted_key=config.encrypted_key,key_version=config.key_version,key_mask='已设置',create_request_id=uuid4(),create_fingerprint='x'*64,enabled=True,is_default=True))
            db.add(MainQuest(id=qid,user_id=uid,title='测试：整理工作空间',description='虚构验收目标',status='active'));db.flush()
            db.add(Task(id=tid,user_id=uid,title='测试：整理桌面',description='虚构验收场景：只想把桌面上三支笔收进笔筒，请拆为简单小动作。',main_quest_id=qid))
            db.add(StateSnapshot(id=snapshot_id,user_id=uid,request_id=uuid4(),fingerprint='x'*64,pressure=80,energy=35,difficulty='虚构测试：怕事情太多，不知道从哪开始'));db.flush()
            db.add(StateCurrent(user_id=uid,snapshot_id=snapshot_id,generation=1))
        created=True
        app=create_app(settings);app.state.database.dispose();app.state.database.engine=engine;app.state.database.sessions=sessions
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8765,log_level='error',access_log=False))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        for _ in range(100):
            if server.started:break
            time.sleep(.1)
        assert server.started
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            context=browser.new_context(viewport={'width':1440,'height':1100},reduced_motion='reduce')
            context.add_cookies([{'name':'camp_session','value':token,'url':'http://127.0.0.1:8765'}])
            page=context.new_page();page.set_default_timeout(60000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto('http://127.0.0.1:8765/tasks/'+str(tid))
            with page.expect_response(lambda r:r.url.endswith('/api/startup/breakdowns') and r.request.method=='POST',timeout=120000) as first_response:
                page.get_by_role('link',name='拆解',exact=True).click()
            first_result=first_response.value.json();print('FIRST_RESPONSE',first_result.get('status'),first_result.get('error_code'),flush=True)
            assert first_result.get('status')=='draft','Provider failed: '+str(first_result.get('error_code'))
            expect(page.locator('#breakdown-confirm')).to_be_visible(timeout=120000)
            with sessions() as db:
                assert db.scalar(select(func.count()).select_from(Task).where(Task.parent_task_id==tid))==0
                first=db.scalar(select(BreakdownPlan).where(BreakdownPlan.user_id==uid));first_id=first.id
                print('LIVE_FIRST',first.status,len(first.advice['steps']),flush=True)
            page.locator('#breakdown-feedback').fill('第一步还是有点难，今天只想花一分钟。请只保留一个更容易的小动作。')
            with page.expect_response(lambda r:r.url.endswith('/api/startup/breakdowns') and r.request.method=='POST',timeout=120000) as second_response:
                page.locator('#breakdown-generate').click()
            second_result=second_response.value.json();print('SECOND_RESPONSE',second_result.get('status'),second_result.get('error_code'),flush=True)
            assert second_result.get('status')=='draft','Follow-up failed: '+str(second_result.get('error_code'))
            expect(page.locator('#breakdown-generate')).to_be_enabled(timeout=120000)
            expect(page.locator('#breakdown-confirm')).to_be_visible(timeout=120000)
            with sessions() as db:
                plans=list(db.scalars(select(BreakdownPlan).where(BreakdownPlan.user_id==uid).order_by(BreakdownPlan.created_at)))
                assert len(plans)==2 and plans[0].status=='superseded' and plans[1].status=='draft'
                print('LIVE_REGENERATED',len(plans[1].advice['steps']),flush=True)
            title=page.locator('[data-field="title"]').first;title.fill('验收：'+title.input_value()[:150])
            expect(page.locator('#breakdown-confirm')).to_be_disabled();page.locator('#breakdown-edit').click();expect(page.locator('#breakdown-confirm')).to_be_enabled()
            selected=page.locator('[data-selected]')
            for index in range(1,selected.count()):selected.nth(index).uncheck()
            page.locator('#breakdown-confirm').click();expect(page.locator('#breakdown-start')).to_be_visible()
            with sessions() as db:
                assert db.scalar(select(func.count()).select_from(Task).where(Task.parent_task_id==tid))==1
                logs=list(db.scalars(select(AICallLog).where(AICallLog.user_id==uid)));assert len(logs)==2
                print('LIVE_USAGE',[(log.status,log.usage) for log in logs],flush=True)
            assert 'generate=' not in page.url
            page.reload()
            expect(page.locator('#breakdown-start')).to_be_visible()
            page.evaluate('scrollTo(0,0)');page.screenshot(path=str(out/'live-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844});page.evaluate('scrollTo(0,0)');expect(page.locator('#sidebar')).to_be_hidden()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(out/'live-mobile.png'),full_page=True)
            page.locator('#breakdown-start').click();expect(page).to_have_url(__import__('re').compile('/focus\?task='))
            page.get_by_role('button',name='开始专注',exact=True).click();expect(page.get_by_role('heading',name='专注中',exact=True)).to_be_visible()
            page.get_by_role('button',name='结束并保存记录',exact=True).click();expect(page.get_by_role('link',name='查看历练手记 →')).to_be_visible()
            with sessions() as db:
                focus=db.scalar(select(FocusSession).where(FocusSession.user_id==uid));assert focus.status=='finished'
                task=db.get(Task,focus.task_id);assert task.parent_task_id==tid and task.status=='todo'
                assert db.scalar(select(func.count()).select_from(AICallLog).where(AICallLog.user_id==uid))==2
            assert not errors,errors
            print('LIVE_BROWSER_PASS: real AI two turns / edit / confirm one child / reload / real focus start-finish / mobile layout',flush=True)
            browser.close()
    except Exception as exc:
        print('LIVE_FAILED',type(exc).__name__,str(exc)[:180] if isinstance(exc,AssertionError) else '',flush=True)
        if created:
            with sessions() as db:
                print('CALL_DIAGNOSTICS',[(c.status,c.error_code,c.usage) for c in db.scalars(select(AICallLog).where(AICallLog.user_id==uid))],flush=True)
        raise
    finally:
        if server:server.should_exit=True
        if thread:thread.join(timeout=10)
        if created:
            with sessions.begin() as db:
                for model in [FocusSegment,ActivityLog,FocusSession,RecommendationBatch,TaskAnalysis,BreakdownPlan,StateCurrent,StateSnapshot,AICallLog,AIConfig,TaskCommand,TaskEvent,QuestEvent,LoginSession]:db.execute(delete(model).where(model.user_id==uid))
                db.execute(delete(Task).where(Task.user_id==uid,Task.parent_task_id.is_not(None)))
                db.execute(delete(Task).where(Task.user_id==uid));db.execute(delete(MainQuest).where(MainQuest.user_id==uid));db.execute(delete(User).where(User.id==uid))
            print('TEMP_USER_CLEANED',flush=True)
        gateway.post_json=original_transport
        engine.dispose()


if __name__=='__main__':run()
