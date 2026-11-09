"""Authenticated, server-rendered task forms; all mutations use one service."""
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.core.config import ROOT
from app.modules.identity.service import current_user
from app.modules.quests.models import MainQuest, Milestone
from app.modules.quests.router import back, same_origin
from app.modules.tasks import service
from app.modules.tasks.models import Task, TaskEvent

router = APIRouter()
templates = Jinja2Templates(directory=ROOT / "app/templates")
templates.env.globals["command_id"] = lambda: str(uuid4())


def render(request: Request, view: str, status_code: int = 200, **context):
    from app.main import PAGES
    return templates.TemplateResponse(request=request, name="tasks.html", status_code=status_code, context={
        "view": view, "app_name": request.app.state.settings.app_name, "pages": PAGES, "page": "tasks",
        "current": PAGES["tasks"], "statuses": service.STATUSES, "priorities": service.PRIORITIES,
        "repeats": service.REPEATS, "event_labels": service.EVENTS, **context,
    })


def choices(db, user_id):
    quests = list(db.scalars(select(MainQuest).where(MainQuest.user_id == user_id, MainQuest.deleted_at.is_(None),
                                                  MainQuest.status != "archived").order_by(MainQuest.title)))
    milestones = list(db.scalars(select(Milestone).where(Milestone.user_id == user_id, Milestone.deleted_at.is_(None),
                           Milestone.main_quest_id.in_([q.id for q in quests])).order_by(Milestone.title)))
    return {"quests": quests, "milestones": milestones}


@router.get("/tasks")
def task_list(request: Request, status: str = "", category: str = "", quest: str = "", deleted: bool = False):
    with request.app.state.database.transaction() as db:
        user = current_user(db, request.cookies.get("camp_session"))
        if not user:
            return back("/account")
        try:
            tasks = service.list_tasks(db, user.id, status=status, category=category, quest_id=service.identifier(quest), deleted=deleted)
        except service.TaskError as error:
            return render(request, "error", error=str(error), status_code=error.status_code)
        return render(request, "list", tasks=tasks, unavailable=service.unavailable_reasons(db, user.id, tasks),
                      filters={"status": status, "category": category, "quest": str(quest or ""), "deleted": deleted}, **choices(db, user.id))


@router.get("/tasks/new")
def task_new(request: Request, quest: UUID | None = None, milestone: UUID | None = None, parent: UUID | None = None):
    with request.app.state.database.transaction() as db:
        user = current_user(db, request.cookies.get("camp_session"))
        if not user:
            return back("/account")
        try:
            parent_task = service.get_task(db, user.id, parent) if parent else None
            if parent_task:
                service.ensure_available(db, parent_task)
                quest, milestone = parent_task.main_quest_id, parent_task.milestone_id
            service.validate_links(db, user.id, {"main_quest_id": quest, "milestone_id": milestone})
            return render(request, "new", values={"main_quest_id": quest, "milestone_id": milestone},
                          parent=parent_task, **choices(db, user.id))
        except service.TaskError as error:
            return render(request, "error", error=str(error), status_code=error.status_code)


@router.get("/tasks/{task_id}")
def task_detail(request: Request, task_id: UUID):
    with request.app.state.database.transaction() as db:
        user = current_user(db, request.cookies.get("camp_session"))
        if not user:
            return back("/account")
        try:
            task = service.get_task(db, user.id, task_id)
            events = list(db.scalars(select(TaskEvent).where(TaskEvent.task_id == task.id, TaskEvent.user_id == user.id).order_by(TaskEvent.created_at.desc(), TaskEvent.id.desc())))
            available_error = None
            if not task.deleted_at:
                try:
                    service.ensure_available(db, task)
                except service.TaskError as error:
                    available_error = str(error)
            return render(request, "detail", task=task, values=service.snapshot(task),
                          parent=service.get_task(db, user.id, task.parent_task_id) if task.parent_task_id else None,
                          children=service.children(db, task, include_deleted=True), events=events,
                          local_zone=ZoneInfo(user.timezone), available_error=available_error, **choices(db, user.id))
        except service.TaskError as error:
            return render(request, "error", error=str(error), status_code=error.status_code)


def mutate(request: Request, action: str, form, task_id: UUID | None = None):
    try:
        with request.app.state.database.transaction() as db:
            user = current_user(db, request.cookies.get("camp_session"))
            if not user:
                return back("/account")
            request_id = service.identifier(form.get("request_id"))
            if not request_id:
                raise service.TaskError("缺少提交编号，请刷新页面", 400)
            ids, versions = [], None
            if action == "batch":
                action = str(form.get("action", ""))
                if action not in {"status", "delete", "restore"}:
                    raise service.TaskError("批量操作无效")
                selected = form.getlist("selected")
                if len(selected) > 100:
                    raise service.TaskError("每批最多 100 个任务")
                versions = {}
                for value in selected:
                    raw_id, raw_version = str(value).split(":", 1)
                    item_id = service.identifier(raw_id)
                    if not item_id:
                        raise service.TaskError("任务编号无效")
                    ids.append(item_id)
                    versions[str(item_id)] = int(raw_version)
            elif task_id:
                ids, versions = [task_id], {str(task_id): int(str(form.get("version", "0")))}
            data = {key: str(form.get(key, "")) for key in
                    ("title", "description", "category", "priority", "due_date", "repeat_rule", "main_quest_id", "milestone_id", "parent_task_id")} if action in {"create", "edit"} else {}
            if action == "status":
                data = {"status": str(form.get("status", ""))}
            result = service.execute(db, user.id, request_id, action, data, ids, versions)
            return back(f"/tasks/{result}" if result and action != "delete" else "/tasks")
    except (ValueError, TypeError) as error:
        message = str(error) if isinstance(error, service.TaskError) else "输入无效，请检查标题、日期和提交内容"
        return render(request, "error", error=message, status_code=getattr(error, "status_code", 400))


@router.post("/tasks/create")
async def task_create(request: Request):
    same_origin(request)
    form = await request.form()
    return await run_in_threadpool(mutate, request, "create", form)


@router.post("/tasks/batch")
async def task_batch(request: Request):
    same_origin(request)
    form = await request.form()
    return await run_in_threadpool(mutate, request, "batch", form)


@router.post("/tasks/{task_id}/{action}")
async def task_action(request: Request, task_id: UUID, action: str):
    same_origin(request)
    if action not in {"edit", "status", "delete", "restore"}:
        return render(request, "error", error="操作不存在", status_code=404)
    form = await request.form()
    return await run_in_threadpool(mutate, request, action, form, task_id)
