"""Explicit --live test: synthetic independent items, real provider/DB/browser."""
import secrets
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright, expect
from sqlalchemy import delete, func, select
from app.core.config import Settings
from app.main import create_app
from app.modules.identity.models import User, LoginSession
from app.modules.identity.service import token_hash
from app.modules.ai_gateway.models import AIConfig, AICallLog
from app.modules.startup_items.models import StartupItem
from app.modules.startup_items.schemas import Create
from app.modules.startup_items.service import create
from app.modules.startup_state.models import StateCurrent, StateSnapshot


def run():
    assert '--live' in sys.argv
    app = create_app(Settings(log_level='ERROR'))
    database = app.state.database
    uid, token = uuid4(), secrets.token_urlsafe(32)
    server = None
    thread = None
    try:
        with database.transaction() as db:
            config = db.scalar(select(AIConfig).where(AIConfig.is_default.is_(True), AIConfig.deleted_at.is_(None), AIConfig.enabled.is_(True)))
            assert config, 'No model configured'
            db.add(User(id=uid, username='analysis_probe_' + uid.hex, password_hash='unused-test-only',
                display_name='事项分析合成验收', timezone='Asia/Shanghai'))
            db.flush()
            db.add(LoginSession(user_id=uid, token_hash=token_hash(token), expires_at=datetime.now(timezone.utc)+timedelta(hours=1)))
            db.add(AIConfig(user_id=uid, name='合成验收模型', base_url=config.base_url, model_id=config.model_id,
                encrypted_key=config.encrypted_key, key_version=config.key_version, key_mask='已设置',
                create_request_id=uuid4(), create_fingerprint='x'*64, enabled=True, is_default=True))
            for description, importance, urgency, progress in [
                ('合成：给已定位的排序函数 Bug 补一条边界测试并修复',85,80,'已找到空列表时的报错位置，测试文件已打开'),
                ('合成：阅读一篇介绍 AI 工具的技术文章',40,20,'已选好文章，今天只需要读开头两段，不做复杂研究'),
                ('合成：把桌面三支笔放进笔筒，整理开发资料',35,30,'已经清理一半桌面，剩余动作只需动手整理')]:
                create(db, uid, Create(description=description, importance=importance, urgency=urgency,
                    progress=progress, request_id=uuid4()))
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8772, log_level='error', access_log=False))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            context = browser.new_context(viewport={'width':1440,'height':1100},reduced_motion='reduce')
            context.add_cookies([{'name':'camp_session','value':token,'url':'http://127.0.0.1:8772'}])
            page = context.new_page()
            errors = []
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto('http://127.0.0.1:8772/startup')
            expect(page.locator('.startup-item')).to_have_count(3, timeout=20000)
            page.locator('#items-analyze').click()
            expect(page.locator('#items-analysis-message')).to_contain_text('本次：', timeout=240000)
            with database.transaction() as db:
                rows=list(db.scalars(select(StartupItem).where(StartupItem.user_id==uid)))
                logs=list(db.scalars(select(AICallLog).where(AICallLog.user_id==uid)))
                print('LIVE_DIAGNOSTICS',[(r.analysis_attempt_status,r.analysis_error,r.analysis_result.get('quadrant') if r.analysis_result else None) for r in rows],
                      'CALLS',[(log.status,log.error_code,log.usage) for log in logs],flush=True)
                assert all(r.analysis_result and r.analysis_result['item_id']==str(r.id) and r.analysis_result['quadrant'] for r in rows)
                count=len(logs)
                assert count==3
            expect(page.locator('.item-marker')).to_have_count(3)
            page.locator('#items-analyze').click()
            expect(page.locator('#items-analysis-message')).to_contain_text('复用 3 件缓存', timeout=30000)
            page.reload()
            expect(page.locator('.item-marker')).to_have_count(3,timeout=20000)
            page.evaluate("() => {for(const [id,value] of [['pressure',80],['energy',25]]){const n=document.getElementById(id);n.value=value;n.dispatchEvent(new Event('input'));}}")
            expect(page.locator('#state-message')).to_have_text('已自动保存', timeout=20000)
            with database.transaction() as db:
                assert db.scalar(select(func.count()).select_from(AICallLog).where(AICallLog.user_id==uid))==count
            marker=page.locator('.item-marker').first
            marker.hover()
            expect(page.locator('#item-scatter-tooltip')).to_contain_text('启动动作：')
            marker.click()
            expect(page.locator('#item-form')).to_be_visible()
            page.locator('#item-progress').fill('合成修改：目前已经多完成一个小动作')
            page.locator('#item-form button[type=submit]').click()
            expect(page.locator('.item-marker')).to_have_count(2,timeout=20000)
            page.set_viewport_size({'width':390,'height':844})
            expect(page.locator('#sidebar')).to_be_hidden()
            page.wait_for_function("()=>document.querySelector('.state-chart').clientHeight<=Math.max(document.querySelector('.state-chart').clientWidth,268)+5")
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            out=Path(tempfile.gettempdir())/'adventure-v3-analysis';out.mkdir(exist_ok=True)
            page.evaluate('scrollTo(0,0)');page.screenshot(path=str(out/'mobile.png'),full_page=True)
            assert not errors,errors
            browser.close()
        print('LIVE_PASS real provider/DB/browser: 3 classifications/cache/reload/no-slider-AI/tooltip/edit-stale/390px',flush=True)
    finally:
        if server:server.should_exit=True
        if thread:thread.join(10)
        with database.transaction() as db:
            for model in (StateCurrent,StateSnapshot,StartupItem,AICallLog,AIConfig,LoginSession):
                db.execute(delete(model).where(model.user_id==uid))
            db.execute(delete(User).where(User.id==uid))
        database.dispose()


if __name__=='__main__':run()
