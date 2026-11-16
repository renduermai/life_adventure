"""Explicit --live browser/DB probe using a disposable synthetic account; no AI."""
import secrets
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright, expect
from sqlalchemy import delete, select
from app.core.config import Settings
from app.main import create_app
from app.modules.identity.models import User, LoginSession
from app.modules.identity.service import token_hash
from app.modules.startup_items.models import StartupItem


def run():
    assert '--live' in sys.argv
    app = create_app(Settings(log_level='ERROR'))
    database = app.state.database
    uid, token = uuid4(), secrets.token_urlsafe(32)
    server = None
    thread = None
    try:
        with database.transaction() as db:
            db.add(User(id=uid, username='items_probe_' + uid.hex, password_hash='unused-test-only',
                display_name='合成事项验收', timezone='Asia/Shanghai'))
            db.flush()
            db.add(LoginSession(user_id=uid, token_hash=token_hash(token),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8770, log_level='error', access_log=False))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            context = browser.new_context()
            context.add_cookies([{'name': 'camp_session', 'value': token, 'url': 'http://127.0.0.1:8770'}])
            page = context.new_page()
            page.goto('http://127.0.0.1:8770/startup')
            expect(page.locator('#items-list')).to_contain_text('还没有记录事情', timeout=20000)
            page.locator('#item-new').click()
            page.locator('#item-description').fill('合成：整理三支笔')
            page.locator('#item-importance').fill('35')
            page.locator('#item-urgency').fill('30')
            page.locator('#item-progress').fill('已经整理一支')
            page.locator('#item-form button[type=submit]').click()
            expect(page.locator('.startup-item')).to_have_count(1, timeout=20000)
            page.reload()
            expect(page.locator('.startup-item')).to_contain_text('已经整理一支', timeout=20000)
            page.locator('.startup-item').get_by_role('button', name='编辑').click()
            page.locator('#item-progress').fill('已经整理两支')
            page.locator('#item-form button[type=submit]').click()
            expect(page.locator('.startup-item')).to_contain_text('已经整理两支', timeout=20000)
            with database.transaction() as db:
                item = db.scalar(select(StartupItem).where(StartupItem.user_id == uid))
                assert item.progress == '已经整理两支' and (item.importance, item.urgency) == (35, 30)
            page.once('dialog', lambda dialog: dialog.accept())
            page.locator('.startup-item').get_by_role('button', name='删除').click()
            expect(page.locator('.startup-item')).to_have_count(0, timeout=20000)
            with database.transaction() as db:
                assert db.scalar(select(StartupItem).where(StartupItem.user_id == uid)).deleted_at is not None
            browser.close()
        print('LIVE_PASS real browser + PostgreSQL: create / reload / edit / new connection read / soft delete; synthetic account')
    finally:
        if server:
            server.should_exit = True
        if thread:
            thread.join(10)
        with database.transaction() as db:
            db.execute(delete(StartupItem).where(StartupItem.user_id == uid))
            db.execute(delete(LoginSession).where(LoginSession.user_id == uid))
            db.execute(delete(User).where(User.id == uid))
        database.dispose()


if __name__ == '__main__':
    run()
