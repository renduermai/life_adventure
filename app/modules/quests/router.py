"""Local browser interface for identity and quests."""
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select

from app.core.config import ROOT
from app.modules.identity.models import LoginSession
from app.modules.identity.service import current_user, lock_user, login, register, token_hash, update_profile
from app.modules.quests.models import MainQuest, Milestone, QuestEvent
from app.modules.quests.service import create_milestone, get_milestone, get_quest, quest_progress, set_milestone_fields, set_quest_fields, soft_delete

router = APIRouter()
templates = Jinja2Templates(directory=ROOT / "app/templates")


def same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        raise HTTPException(403, "缺少来源信息，请通过本应用页面操作")
    parsed = urlsplit(origin)
    if parsed.scheme != request.url.scheme or parsed.netloc != request.url.netloc:
        raise HTTPException(403, "请求来源无效")


def render(request: Request, view: str, **context):
    from app.main import PAGES
    return templates.TemplateResponse(request=request, name="quests.html", context={
        "view": view, "app_name": request.app.state.settings.app_name,
        "pages": PAGES, "page": "quests", "current": {"title": "主线与里程碑", "subtitle": "一步一步，把重要的事带到现实。"}, **context,
    })


def back(path: str):
    return RedirectResponse(path, status_code=303)


def record_event(db, quest, action: str, detail: str = ""):
    db.add(QuestEvent(user_id=quest.user_id, main_quest_id=quest.id, action=action, detail=detail[:200]))


@router.get("/account")
def account(request: Request):
    with request.app.state.database.transaction() as db:
        user = current_user(db, request.cookies.get("camp_session"))
        return render(request, "account", user=user)


@router.post("/account/{action}")
async def account_post(request: Request, action: str):
    same_origin(request)
    form = await request.form()
    token = request.cookies.get("camp_session")
    try:
        with request.app.state.database.transaction() as db:
            user = current_user(db, token)
            if action == "register":
                register(db, str(form.get("username", "")), str(form.get("password", "")), str(form.get("display_name", "")))
                return back("/account")
            if action == "login":
                token = login(db, str(form.get("username", "")), str(form.get("password", "")))
                response = back("/quests")
                response.set_cookie("camp_session", token, httponly=True, samesite="strict", secure=request.url.scheme == "https", max_age=604800, path="/")
                return response
            if not user:
                raise HTTPException(401, "请先登录")
            if action == "profile":
                update_profile(user, str(form.get("display_name", "")), str(form.get("timezone", "")))
                return back("/account")
            if action == "logout":
                db.execute(delete(LoginSession).where(LoginSession.token_hash == token_hash(token)))
                response = back("/account")
                response.delete_cookie("camp_session", path="/")
                return response
            raise HTTPException(404)
    except ValueError as error:
        return render(request, "account", user=None, error=str(error))


@router.get("/quests")
def quest_list(request: Request):
    with request.app.state.database.transaction() as db:
        user = current_user(db, request.cookies.get("camp_session"))
        if not user:
            return back("/account")
        quests = db.scalars(select(MainQuest).where(MainQuest.user_id == user.id).order_by(MainQuest.created_at.desc())).all()
        return render(request, "list", user=user, quests=quests)


@router.post("/quests/create")
async def quest_create(request: Request):
    same_origin(request)
    form = await request.form()
    with request.app.state.database.transaction() as db:
        user = current_user(db, request.cookies.get("camp_session"))
        if not user:
            return back("/account")
        lock_user(db, user.id)
        quest = MainQuest(user_id=user.id, status="active")
        try:
            set_quest_fields(quest, str(form.get("title", "")), str(form.get("description", "")), str(form.get("start_date", "")), str(form.get("due_date", "")))
        except ValueError as error:
            quests = db.scalars(select(MainQuest).where(MainQuest.user_id == user.id).order_by(MainQuest.created_at.desc())).all()
            return render(request, "list", user=user, quests=quests, error=str(error))
        db.add(quest)
        db.flush()
        record_event(db, quest, "创建主线", quest.title)
        return back(f"/quests/{quest.id}")


@router.get("/quests/{quest_id}")
def quest_detail(request: Request, quest_id: UUID):
    with request.app.state.database.transaction() as db:
        user = current_user(db, request.cookies.get("camp_session"))
        if not user:
            return back("/account")
        quest = get_quest(db, user.id, quest_id)
        if not quest:
            raise HTTPException(404, "主线不存在")
        milestones = db.scalars(select(Milestone).where(Milestone.user_id == user.id, Milestone.main_quest_id == quest_id).order_by(Milestone.sort_order, Milestone.created_at)).all()
        value = quest_progress(db, user.id, quest_id, milestones)
        events = db.scalars(select(QuestEvent).where(QuestEvent.user_id == user.id, QuestEvent.main_quest_id == quest_id).order_by(QuestEvent.created_at.desc())).all()
        return render(request, "detail", user=user, quest=quest, milestones=milestones, **value, events=events)


@router.post("/quests/{quest_id}/{action}")
async def quest_action(request: Request, quest_id: UUID, action: str):
    same_origin(request)
    form = await request.form()
    with request.app.state.database.transaction() as db:
        user = current_user(db, request.cookies.get("camp_session"))
        if not user:
            return back("/account")
        lock_user(db, user.id)
        quest = get_quest(db, user.id, quest_id, deleted=action == "restore")
        if not quest:
            raise HTTPException(404, "主线不存在")
        try:
            if action == "edit":
                set_quest_fields(quest, str(form.get("title", "")), str(form.get("description", "")), str(form.get("start_date", "")), str(form.get("due_date", "")))
            elif action == "status":
                status = str(form.get("status", ""))
                if status not in {"active", "paused", "completed", "archived"}:
                    raise ValueError("状态无效")
                quest.status = status
            elif action == "delete":
                soft_delete(quest)
            elif action == "restore":
                quest.deleted_at = None
            elif action == "milestones":
                create_milestone(db, user.id, quest.id, str(form.get("title", "")), str(form.get("description", "")), str(form.get("due_date", "")))
            else:
                raise HTTPException(404)
            labels = {"edit": "修改主线", "status": "更新主线状态", "delete": "删除主线", "restore": "恢复主线", "milestones": "添加里程碑"}
            details = {"status": quest.status, "milestones": str(form.get("title", ""))}
            if action != "milestones":
                record_event(db, quest, labels[action], details.get(action, ""))
        except ValueError as error:
            milestones = db.scalars(select(Milestone).where(Milestone.user_id == user.id, Milestone.main_quest_id == quest_id)).all()
            return render(request, "detail", user=user, quest=quest, milestones=milestones, **quest_progress(db, user.id, quest_id, milestones), error=str(error))
        return back("/quests" if action == "delete" else f"/quests/{quest.id}")


@router.post("/quests/{quest_id}/milestones/{milestone_id}/{action}")
async def milestone_action(request: Request, quest_id: UUID, milestone_id: UUID, action: str):
    same_origin(request)
    form = await request.form()
    with request.app.state.database.transaction() as db:
        user = current_user(db, request.cookies.get("camp_session"))
        if not user:
            return back("/account")
        lock_user(db, user.id)
        if not get_quest(db, user.id, quest_id):
            raise HTTPException(404)
        item = get_milestone(db, user.id, quest_id, milestone_id, deleted=action == "restore")
        if not item:
            raise HTTPException(404)
        try:
            if action == "edit":
                set_milestone_fields(item, str(form.get("title", "")), str(form.get("description", "")), str(form.get("due_date", "")))
            elif action == "toggle":
                status = str(form.get("status", ""))
                if status not in {"pending", "completed"}:
                    raise ValueError("状态无效")
                item.status = status
            elif action == "delete":
                soft_delete(item)
            elif action == "restore":
                item.deleted_at = None
            else:
                raise HTTPException(404)
            quest = get_quest(db, user.id, quest_id)
            record_event(db, quest, {"edit": "修改里程碑", "toggle": "更新里程碑状态", "delete": "删除里程碑", "restore": "恢复里程碑"}[action], item.title)
        except ValueError as error:
            milestones = db.scalars(select(Milestone).where(Milestone.user_id == user.id, Milestone.main_quest_id == quest_id)).all()
            quest = get_quest(db, user.id, quest_id)
            return render(request, "detail", user=user, quest=quest, milestones=milestones, **quest_progress(db, user.id, quest_id, milestones), error=str(error))
        return back(f"/quests/{quest_id}")
