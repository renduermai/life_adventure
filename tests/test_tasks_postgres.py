"""Opt-in PostgreSQL tests; every write is inside a unique disposable schema."""
import os
import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.config import ROOT, Settings, postgres_url
from app.main import create_app
from app.modules.identity.models import LoginSession, User
from app.modules.identity.service import token_hash
from app.modules.quests.models import MainQuest, Milestone
from app.modules.quests.service import quest_progress
from app.modules.tasks import service
from app.modules.tasks.models import Task, TaskCommand, TaskEvent

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def task_engine():
    raw = os.environ.get("TEST_DATABASE_URL")
    if not raw:
        pytest.skip("TEST_DATABASE_URL 未配置；任务真实 PostgreSQL 测试未运行")
    url = postgres_url(raw)
    schema = "ac_tasks_test_" + uuid4().hex
    admin = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 5})
    engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 5,
                           "options": f"-c search_path={schema} -c statement_timeout=15000"})
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        with engine.begin() as conn:
            assert conn.execute(text("SELECT current_schema()")).scalar_one() == schema
            config = Config(str(ROOT / "alembic.ini"))
            config.attributes["connection"] = conn
            command.upgrade(config, "head")
            command.check(config)
        yield engine
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.downgrade(config, "0003_quest_events")
            assert conn.execute(text("SELECT to_regclass('tasks')")).scalar_one() is None
            command.upgrade(config, "head")
            command.check(config)
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def camp(task_engine):
    sessions = sessionmaker(task_engine, expire_on_commit=False)
    user_id, other_id, quest_id, milestone_id = uuid4(), uuid4(), uuid4(), uuid4()
    with sessions.begin() as db:
        db.add_all([User(id=i, username="test_" + i.hex, password_hash="unused-test-only", display_name="测试冒险者", timezone="Asia/Shanghai") for i in (user_id, other_id)])
        db.flush()
        db.add(MainQuest(id=quest_id, user_id=user_id, title="测试主线", status="active"))
        db.flush()
        db.add(Milestone(id=milestone_id, user_id=user_id, main_quest_id=quest_id, title="测试里程碑"))
        db.add(LoginSession(user_id=user_id, token_hash=token_hash(str(user_id)), expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
    return dict(sessions=sessions, user=user_id, other=other_id, quest=quest_id, milestone=milestone_id, engine=task_engine)


def create(camp, **values):
    with camp["sessions"].begin() as db:
        return service.execute(db, camp["user"], uuid4(), "create", {"title": "任务", **values})


def change(camp, task_id, action="status", data=None, request_id=None, version=None):
    with camp["sessions"].begin() as db:
        task = service.get_task(db, camp["user"], task_id)
        return service.execute(db, camp["user"], request_id or uuid4(), action, data or {"status": "completed"},
                               [task_id], {str(task_id): version or task.version})


def test_crud_completion_reversal_idempotency_and_persistence(camp):
    task_id = create(camp, title="第一次", category="学习", priority="high", due_date="2026-12-31")
    change(camp, task_id, "edit", {"title": "修改后", "category": "工作", "priority": "low"})
    request_id = uuid4()
    change(camp, task_id, request_id=request_id, version=2)
    change(camp, task_id, request_id=request_id, version=2)
    change(camp, task_id)  # same status with fresh request also does not add a completion
    with camp["sessions"].begin() as db:
        task = service.get_task(db, camp["user"], task_id)
        assert (task.title, task.category, task.status, task.completion_round) == ("修改后", "工作", "completed", 1)
        assert db.scalar(select(func.count()).select_from(TaskEvent).where(TaskEvent.task_id == task_id, TaskEvent.kind == "completed")) == 1
    change(camp, task_id, data={"status": "todo"})
    change(camp, task_id)
    change(camp, task_id, "delete")
    change(camp, task_id, "restore")
    camp["engine"].dispose()
    with camp["sessions"].begin() as db:
        task = service.get_task(db, camp["user"], task_id)
        assert task.status == "completed" and task.deleted_at is None and task.completion_round == 2
        events = list(db.scalars(select(TaskEvent).where(TaskEvent.task_id == task_id)))
        reversed_event = next(e for e in events if e.kind == "reopened")
        assert reversed_event.reversal_of in [e.id for e in events if e.kind == "completed"]


def test_repeat_completion_generates_only_one_successor(camp):
    task_id = create(camp, repeat_rule="monthly", due_date="2028-01-31")
    change(camp, task_id)
    change(camp, task_id, data={"status": "todo"})
    change(camp, task_id)
    with camp["sessions"].begin() as db:
        successors = list(db.scalars(select(Task).where(Task.recurrence_from_id == task_id)))
        assert len(successors) == 1 and successors[0].due_date == date(2028, 2, 29)
        assert successors[0].status == "todo"


def test_parent_child_and_progress_rules(camp):
    parent = create(camp, main_quest_id=str(camp["quest"]), milestone_id=str(camp["milestone"]))
    first = create(camp, parent_task_id=str(parent))
    second = create(camp, parent_task_id=str(parent))
    with pytest.raises(service.TaskError):
        create(camp, parent_task_id=str(first))
    with pytest.raises(service.TaskError):
        change(camp, parent)
    change(camp, first)
    with camp["sessions"].begin() as db:
        assert service.progress_counts(db, camp["user"], camp["quest"]) == (1, 2)
        assert quest_progress(db, camp["user"], camp["quest"], [])['progress'] == 50
    change(camp, second)
    change(camp, parent)
    change(camp, first, data={"status": "in_progress"})
    with camp["sessions"].begin() as db:
        assert service.get_task(db, camp["user"], parent).status == "todo"
    change(camp, parent, "delete")
    with pytest.raises(service.TaskError):
        change(camp, first)
    with camp["sessions"].begin() as db:
        assert service.progress_counts(db, camp["user"], camp["quest"]) == (0, 0)
    change(camp, parent, "restore")
    change(camp, first, "delete")
    change(camp, parent)
    change(camp, first, "restore")
    with camp["sessions"].begin() as db:
        assert service.get_task(db, camp["user"], parent).status == "todo"
    change(camp, parent, "edit", {"title": "移到独立任务"})
    with camp["sessions"].begin() as db:
        assert service.get_task(db, camp["user"], second).main_quest_id is None


def test_invalid_cross_owner_and_mismatched_associations(camp):
    task = create(camp)
    with camp["sessions"].begin() as db:
        with pytest.raises(service.TaskError):
            service.get_task(db, camp["other"], task)
    with pytest.raises(service.TaskError):
        create(camp, milestone_id=str(camp["milestone"]))
    with pytest.raises(service.TaskError):
        create(camp, main_quest_id=str(uuid4()))
    with camp["sessions"].begin() as db:
        other_quest = MainQuest(user_id=camp["other"], title="另一用户的主线")
        db.add(other_quest)
        db.flush()
        other_quest_id = other_quest.id
    with pytest.raises(service.TaskError):
        create(camp, main_quest_id=str(other_quest_id))
    with pytest.raises(IntegrityError):
        with camp["sessions"].begin() as db:
            db.add(Task(user_id=camp["user"], title="跨用户数据库约束", main_quest_id=other_quest_id))


def test_deleted_and_archived_associations_and_relink(camp):
    task = create(camp, main_quest_id=str(camp["quest"]), milestone_id=str(camp["milestone"]))
    with camp["sessions"].begin() as db:
        db.get(Milestone, camp["milestone"]).deleted_at = datetime.now(timezone.utc)
    with pytest.raises(service.TaskError):
        change(camp, task)
    with camp["sessions"].begin() as db:
        assert service.progress_counts(db, camp["user"], camp["quest"]) == (0, 0)
        db.get(Milestone, camp["milestone"]).deleted_at = None
        db.get(MainQuest, camp["quest"]).status = "archived"
    with pytest.raises(service.TaskError):
        change(camp, task)
    change(camp, task, "edit", {"title": "独立副本"})
    change(camp, task)


def test_batch_all_or_nothing_and_children_first(camp):
    good = create(camp)
    parent = create(camp)
    child = create(camp, parent_task_id=str(parent))
    with pytest.raises(service.TaskError):
        with camp["sessions"].begin() as db:
            service.execute(db, camp["user"], uuid4(), "status", {"status": "completed"}, [good, parent], {str(good): 1, str(parent): 1})
    with camp["sessions"].begin() as db:
        assert service.get_task(db, camp["user"], good).status == "todo"
        service.execute(db, camp["user"], uuid4(), "status", {"status": "completed"}, [parent, child], {str(parent): 1, str(child): 1})
    with camp["sessions"].begin() as db:
        assert service.get_task(db, camp["user"], parent).status == "completed"


def test_stale_versions_and_command_reuse_rejected(camp):
    request_id = uuid4()
    with camp["sessions"].begin() as db:
        task = service.execute(db, camp["user"], request_id, "create", {"title": "one"})
    with camp["sessions"].begin() as db:
        assert service.execute(db, camp["user"], request_id, "create", {"title": "one"}) == task
    with pytest.raises(service.TaskError, match="提交编号"):
        with camp["sessions"].begin() as db:
            service.execute(db, camp["user"], request_id, "create", {"title": "two"})
    change(camp, task)
    with pytest.raises(service.TaskError, match="已被修改"):
        change(camp, task, data={"status": "todo"}, version=1)


def test_concurrent_duplicate_completion(camp):
    task = create(camp, repeat_rule="daily")
    request_id = uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: change(camp, task, request_id=request_id, version=1), range(2)))
    assert results == [task, task]
    with camp["sessions"].begin() as db:
        assert db.scalar(select(func.count()).select_from(TaskEvent).where(TaskEvent.task_id == task, TaskEvent.kind == "completed")) == 1
        assert db.scalar(select(func.count()).select_from(Task).where(Task.recurrence_from_id == task)) == 1


def test_concurrent_different_requests_reject_stale_version(camp):
    task = create(camp)
    def attempt(_):
        try:
            change(camp, task, version=1)
            return "saved"
        except service.TaskError as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sorted(map(str, results)) == ["409", "saved"]
    with camp["sessions"].begin() as db:
        assert db.scalar(select(func.count()).select_from(TaskEvent).where(TaskEvent.task_id == task, TaskEvent.kind == "completed")) == 1


def test_recurrence_children_and_deleted_parent_recovery(camp):
    repeating = create(camp, repeat_rule="daily")
    with pytest.raises(service.TaskError):
        create(camp, parent_task_id=str(repeating))
    parent = create(camp, main_quest_id=str(camp["quest"]))
    child = create(camp, parent_task_id=str(parent))
    with pytest.raises(service.TaskError):
        change(camp, parent, "edit", {"title": "父任务", "repeat_rule": "daily"})
    with pytest.raises(service.TaskError):
        change(camp, child, "edit", {"title": "子任务", "repeat_rule": "weekly"})
    change(camp, parent, "delete")
    change(camp, child, "delete")
    with pytest.raises(service.TaskError):
        change(camp, child, "restore")
    with camp["sessions"].begin() as db:
        items = [service.get_task(db, camp["user"], i) for i in (parent, child)]
        service.execute(db, camp["user"], uuid4(), "restore", {}, [parent, child], {str(t.id): t.version for t in items})
    with camp["sessions"].begin() as db:
        db.get(MainQuest, camp["quest"]).deleted_at = datetime.now(timezone.utc)
    with pytest.raises(service.TaskError):
        change(camp, child)
    with camp["sessions"].begin() as db:
        tasks = service.list_tasks(db, camp["user"])
        assert service.unavailable_reasons(db, camp["user"], tasks)[child] == "关联主线已删除"


def test_database_rejects_milestone_of_another_quest(camp):
    with camp["sessions"].begin() as db:
        quest = MainQuest(user_id=camp["user"], title="另一主线")
        db.add(quest)
        db.flush()
        quest_id = quest.id
    with pytest.raises(service.TaskError):
        create(camp, main_quest_id=str(quest_id), milestone_id=str(camp["milestone"]))
    with pytest.raises(IntegrityError):
        with camp["sessions"].begin() as db:
            db.add(Task(user_id=camp["user"], title="错误关联", main_quest_id=quest_id, milestone_id=camp["milestone"]))


def test_failure_rolls_back_task_event_successor_and_command(camp, monkeypatch):
    task = create(camp, repeat_rule="weekly")
    original = service.event
    def fail(db, task, kind, *args, **kwargs):
        if kind == "recurrence":
            raise RuntimeError("injected failure")
        return original(db, task, kind, *args, **kwargs)
    monkeypatch.setattr(service, "event", fail)
    request_id = uuid4()
    with pytest.raises(RuntimeError):
        change(camp, task, request_id=request_id)
    with camp["sessions"].begin() as db:
        assert service.get_task(db, camp["user"], task).status == "todo"
        assert db.scalar(select(func.count()).select_from(Task).where(Task.recurrence_from_id == task)) == 0
        assert db.scalar(select(func.count()).select_from(TaskEvent).where(TaskEvent.task_id == task, TaskEvent.kind == "completed")) == 0
        assert db.scalar(select(func.count()).select_from(TaskCommand).where(TaskCommand.request_id == request_id)) == 0


@contextmanager
def browser_client(camp):
    app = create_app(Settings(_env_file=None, database_url=None, migration_database_url=None))
    app.state.database.sessions = camp["sessions"]
    with TestClient(app) as client:
        client.cookies.set("camp_session", str(camp["user"]))
        yield client


def test_http_forms_auth_filters_errors_and_quest_progress(camp):
    with browser_client(camp) as client:
        response = client.get(f'/tasks/new?quest={camp["quest"]}&milestone={camp["milestone"]}')
        assert response.status_code == 200
        request_id = re.search(r'name="request_id" value="([^"]+)"', response.text).group(1)
        form = {"request_id": request_id, "title": "<script>示例</script>", "category": "学习", "priority": "high", "repeat_rule": "none",
                "main_quest_id": str(camp["quest"]), "milestone_id": str(camp["milestone"])}
        response = client.post("/tasks/create", data=form, headers={"origin": "http://testserver"})
        assert response.status_code == 200 and "&lt;script&gt;" in response.text
        detail_path = response.url.path
        response = client.get("/tasks?status=todo&category=学习&quest=")
        assert response.status_code == 200 and "&lt;script&gt;" in response.text
        assert client.get("/tasks?status=invalid").status_code == 400
        assert client.get("/tasks?quest=invalid").status_code == 400
        assert client.post(detail_path + "/status", data={"request_id": str(uuid4()), "version": "1", "status": "completed"}, headers={"origin": "http://testserver"}).status_code == 200
        response = client.get(f'/quests/{camp["quest"]}')
        assert "100%" in response.text and "已完成末级任务 1 / 1" in response.text
        client.cookies.set("camp_session", str(camp["other"]))
        assert client.get(detail_path, follow_redirects=False).status_code == 303
        # A valid session for another owner must receive 404 rather than the data.
        with camp["sessions"].begin() as db:
            db.add(LoginSession(user_id=camp["other"], token_hash=token_hash(str(camp["other"])), expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
        assert client.get(detail_path).status_code == 404
        assert client.post(detail_path + "/delete", data={"request_id": str(uuid4()), "version": "2"}, headers={"origin": "http://testserver"}).status_code == 404
        client.cookies.clear()
        assert client.get("/tasks", follow_redirects=False).status_code == 303


def test_http_batch_restore_stale_errors_and_atomic_rollback(camp):
    first, parent = create(camp), create(camp)
    create(camp, parent_task_id=str(parent))
    headers = {"origin": "http://testserver"}
    with browser_client(camp) as client:
        response = client.post("/tasks/batch", data={"request_id": str(uuid4()), "action": "status", "status": "completed",
                              "selected": [f"{first}:1", f"{parent}:1"]}, headers=headers)
        assert response.status_code == 400 and "这次操作没有保存" in response.text
        with camp["sessions"].begin() as db:
            assert service.get_task(db, camp["user"], first).status == "todo"
        assert client.post("/tasks/batch", data={"request_id": str(uuid4()), "action": "delete", "selected": f"{first}:1"}, headers=headers).status_code == 200
        assert "任务" in client.get("/tasks?deleted=true").text
        assert client.post("/tasks/batch", data={"request_id": str(uuid4()), "action": "restore", "selected": f"{first}:2"}, headers=headers).status_code == 200
        assert client.post(f"/tasks/{first}/status", data={"request_id": str(uuid4()), "version": "1", "status": "completed"}, headers=headers).status_code == 409
        assert client.post(f"/tasks/{first}/create", headers=headers).status_code == 404
        assert client.post("/tasks/create", data={"title": "missing token"}, headers=headers).status_code == 400

def test_focus_timer_real_database(camp):
    from app.modules.activity import service as focus
    from app.modules.activity.models import ActivityLog, FocusSegment
    from datetime import timedelta
    task = create(camp)
    req = uuid4()
    with camp['sessions'].begin() as db:
        session = focus.start(db,camp['user'],'countdown','25',task,req)
        session.resumed_at -= timedelta(seconds=10)
    with camp['sessions'].begin() as db:
        session = focus.transition(db,camp['user'],req,'pause')
        assert session.status == 'paused' and session.accumulated_seconds >= 10
    with camp['sessions'].begin() as db:
        assert focus.start(db,camp['user'],'countdown','25',task,req).id == req
        focus.transition(db,camp['user'],req,'resume')
    with camp['sessions'].begin() as db:
        focus.transition(db,camp['user'],req,'finish')
    with camp['sessions'].begin() as db:
        focus.transition(db,camp['user'],req,'finish')
        assert db.scalar(select(func.count()).select_from(ActivityLog).where(ActivityLog.session_id == req)) == 1
        assert db.scalar(select(func.count()).select_from(FocusSegment).where(FocusSegment.session_id == req)) == 2
        with pytest.raises(ValueError):
            focus.transition(db,camp['other'],req,'pause')


def test_focus_single_active_and_invalid_input(camp):
    from app.modules.activity import service as focus
    with pytest.raises(ValueError):
        with camp['sessions'].begin() as db:
            focus.start(db,camp['user'],'countdown','0',None,uuid4())
    with camp['sessions'].begin() as db:
        focus.start(db,camp['user'],'elapsed','',None,uuid4())
    with pytest.raises(ValueError):
        with camp['sessions'].begin() as db:
            focus.start(db,camp['user'],'elapsed','',None,uuid4())

def test_focus_confirmed_duration_and_rollback(camp):
    from app.modules.activity import service as focus
    from app.modules.activity.models import ActivityLog
    request_id = uuid4()
    with camp['sessions'].begin() as db:
        focus.start(db, camp['user'], 'elapsed', '', None, request_id)
    with pytest.raises(ValueError):
        with camp['sessions'].begin() as db:
            focus.transition(db, camp['user'], request_id, 'finish', 999999)
    with camp['sessions'].begin() as db:
        assert focus.active(db, camp['user']).status == 'running'
        focus.transition(db, camp['user'], request_id, 'finish', 0)
    with camp['sessions'].begin() as db:
        log = db.scalar(select(ActivityLog).where(ActivityLog.session_id == request_id))
        assert log.duration_seconds == 0 and '原计时' in log.note


def test_focus_concurrent_finish_is_idempotent(camp):
    from app.modules.activity import service as focus
    from app.modules.activity.models import ActivityLog
    request_id = uuid4()
    with camp['sessions'].begin() as db:
        focus.start(db, camp['user'], 'elapsed', '', None, request_id)
    def finish(_):
        with camp['sessions'].begin() as db:
            return focus.transition(db, camp['user'], request_id, 'finish').id
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(finish, range(2))) == [request_id, request_id]
    with camp['sessions'].begin() as db:
        assert db.scalar(select(func.count()).select_from(ActivityLog).where(ActivityLog.session_id == request_id)) == 1


def test_focus_http_flow(camp):
    with browser_client(camp) as client:
        headers = {'origin':'http://testserver'}
        page = client.get('/focus')
        assert page.status_code == 200 and '开始一次专注' in page.text
        request_id = re.search(r'name="request_id" value="([^"]+)"',page.text).group(1)
        response = client.post('/focus/start',data={'request_id':request_id,'mode':'countdown','minutes':'1'},headers=headers)
        assert response.status_code == 200 and '专注中' in response.text
        assert client.get('/focus').status_code == 200
        response = client.post('/focus/pause',data={'session_id':request_id},headers=headers)
        assert '已暂停' in response.text
        response = client.post('/focus/resume',data={'session_id':request_id},headers=headers)
        assert '专注中' in response.text
        response = client.post('/focus/finish',data={'session_id':request_id,'confirmed_seconds':'0'},headers=headers)
        assert '开始一次专注' in response.text
        assert client.post('/focus/start').status_code == 403

def test_journal_crud_idempotency_and_isolation(camp):
    from app.modules.activity import journal
    from app.modules.activity.models import ActivityEvent
    uid=camp['user']; rid=uuid4(); task=create(camp)
    values={'occurred_at':'2026-11-10T23:30','duration_seconds':'7200','category':'学习','note':'测试','task_id':str(task)}
    with camp['sessions'].begin() as db:
        item=journal.create(db,uid,rid,values)
        assert journal.create(db,uid,rid,values).id==rid
    with pytest.raises(ValueError):
        with camp['sessions'].begin() as db:
            journal.create(db,uid,rid,{**values,'note':'不同'})
    with camp['sessions'].begin() as db:
        start,end,*_=journal.period('day','2026-11-10','Asia/Shanghai')
        assert sum(x.duration_seconds for x in journal.list_logs(db,uid,start,end))==7200
        start,end,*_=journal.period('day','2026-11-11','Asia/Shanghai')
        assert journal.list_logs(db,uid,start,end)==[]
        assert journal.list_logs(db,camp['other'],*journal.period('month','2026-11-10','Asia/Shanghai')[:2])==[]
    with camp['sessions'].begin() as db:
        journal.change(db,uid,rid,1,'edit',{**values,'duration_seconds':'60'})
    with pytest.raises(ValueError):
        with camp['sessions'].begin() as db: journal.change(db,uid,rid,1,'delete',{})
    with pytest.raises(ValueError):
        with camp['sessions'].begin() as db: journal.change(db,camp['other'],rid,2,'delete',{})
    with camp['sessions'].begin() as db:
        journal.change(db,uid,rid,2,'delete',{})
        start,end,*_=journal.period('month','2026-11-10','Asia/Shanghai')
        assert journal.list_logs(db,uid,start,end)==[]
        assert len(journal.list_logs(db,uid,start,end,deleted=True))==1
    with camp['sessions'].begin() as db:
        journal.change(db,uid,rid,3,'restore',{})
    with camp['sessions'].begin() as db:
        assert journal.get_log(db,uid,rid).duration_seconds==60
        assert db.scalar(select(func.count()).select_from(ActivityEvent).where(ActivityEvent.activity_id==rid))==4


def test_journal_timer_http_and_validation(camp):
    from app.modules.activity import service as focus, journal
    from app.modules.activity.models import ActivityLog
    req=uuid4()
    with camp['sessions'].begin() as db: focus.start(db,camp['user'],'elapsed','',None,req)
    with camp['sessions'].begin() as db: focus.transition(db,camp['user'],req,'finish')
    with camp['sessions'].begin() as db:
        log=db.scalar(select(ActivityLog).where(ActivityLog.session_id==req))
        log_id=log.id
        with pytest.raises(ValueError): journal.fields({'occurred_at':'bad','duration_seconds':'0'},'Asia/Shanghai')
    with browser_client(camp) as client:
        headers={'origin':'http://testserver'}
        assert client.get('/journal').status_code==200
        assert client.get('/journal?period=invalid').status_code==400
        page=client.get('/journal?period=day')
        assert '专注计时' in page.text
        assert client.get(f'/journal/{log_id}').status_code==200
        assert client.post(f'/journal/{log_id}/delete',data={'version':'1'},headers=headers).status_code==200
        assert client.get('/journal?period=day&deleted=true').status_code==200
        assert client.post(f'/journal/{log_id}/restore',data={'version':'2'},headers=headers).status_code==200
        assert client.post('/journal/create').status_code==403

def test_reward_completion_reversal_and_repeat(camp):
    from app.modules.growth import service as growth
    from app.modules.growth.models import RewardEntry
    uid=camp['user']; task=create(camp)
    change(camp,task)
    with camp['sessions'].begin() as db:
        assert growth.balances(db,uid)==(10,5)
        rule=growth.settings(db,uid); rule.xp_per_task=25; rule.coins_per_task=3; rule.rule_version+=1
    change(camp,task,data={'status':'todo'})
    with camp['sessions'].begin() as db: assert growth.balances(db,uid)==(0,0)
    change(camp,task)
    with camp['sessions'].begin() as db:
        assert growth.balances(db,uid)==(25,3)
        assert len(list(db.scalars(select(RewardEntry).where(RewardEntry.user_id==uid))))==3
    change(camp,task,'delete')
    with camp['sessions'].begin() as db: assert growth.balances(db,uid)==(25,3)


def test_reward_concurrent_completion_and_rollback(camp,monkeypatch):
    from app.modules.growth import service as growth
    from app.modules.growth.models import RewardEntry
    uid=camp['user']; task=create(camp); req=uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: change(camp,task,request_id=req,version=1),range(2)))==[task,task]
    with camp['sessions'].begin() as db: assert growth.balances(db,uid)==(10,5)
    another=create(camp)
    def fail(*args,**kwargs): raise RuntimeError('injected reward failure')
    monkeypatch.setattr(growth,'grant',fail)
    with pytest.raises(RuntimeError): change(camp,another)
    with camp['sessions'].begin() as db:
        assert service.get_task(db,uid,another).status=='todo'
        assert growth.balances(db,uid)==(10,5)


def test_reward_backfill_and_access(camp):
    from app.modules.growth import service as growth
    from app.modules.growth.models import RewardEntry
    uid=camp['user']; task=create(camp)
    change(camp,task)
    with camp['sessions'].begin() as db:
        assert growth.backfill_current(db,uid)==1
        assert growth.backfill_current(db,uid)==1
        assert growth.balances(db,uid)==(10,5)
        assert growth.balances(db,camp['other'])==(0,0)
    with browser_client(camp) as client:
        assert client.get('/growth').status_code==200
        assert '10 XP' in client.get('/growth').text
        assert client.post('/growth/settings',data={'xp':'30','coins':'8'},headers={'origin':'http://testserver'}).status_code==200
        assert client.post('/growth/settings',data={'xp':'-1','coins':'8'},headers={'origin':'http://testserver'}).status_code==200
        assert client.post('/growth/settings',data={'xp':'30','coins':'8'}).status_code==403

def test_reward_parent_child_reopen(camp):
    from app.modules.growth import service as growth
    uid=camp['user']; parent=create(camp); child=create(camp,parent_task_id=str(parent))
    change(camp,child); change(camp,parent)
    with camp['sessions'].begin() as db: assert growth.balances(db,uid)==(20,10)
    change(camp,child,data={'status':'todo'})
    with camp['sessions'].begin() as db:
        assert growth.balances(db,uid)==(0,0)
        assert service.get_task(db,uid,parent).status=='todo'

def test_dashboard_user_data_and_updates(camp):
    from app.modules.activity.models import ActivityLog
    from zoneinfo import ZoneInfo
    today=datetime.now(ZoneInfo('Asia/Shanghai')).date()
    task=create(camp,title='今日测试副本',due_date=today.isoformat(),main_quest_id=str(camp['quest']))
    with camp['sessions'].begin() as db:
        db.add(ActivityLog(user_id=camp['user'],occurred_at=datetime.now(timezone.utc),duration_seconds=240,category='测试',note='今日历练'))
    with browser_client(camp) as client:
        page=client.get('/')
        assert page.status_code==200 and '测试冒险者' in page.text and '今日测试副本' in page.text and '今日历练' in page.text
        assert '0 XP' in page.text and '测试主线' in page.text
        change(camp,task)
        page=client.get('/')
        assert '10 XP' in page.text and '5 金币' in page.text and '今日测试副本' not in page.text
        with camp['sessions'].begin() as db:
            db.add(LoginSession(user_id=camp['other'],token_hash=token_hash(str(camp['other'])),expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
        client.cookies.set('camp_session',str(camp['other']))
        page=client.get('/')
        assert '今日历练' not in page.text and '测试主线' not in page.text
        assert '还没有进行中的主线' in page.text
        client.cookies.clear()
        assert '登录角色账号' in client.get('/').text
