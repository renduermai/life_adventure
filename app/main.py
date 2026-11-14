"""Adventure Camp application entry point."""
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.config import ROOT, Settings, load_settings
from app.core.database import Database
from app.core.logging import configure_logging

logger = logging.getLogger("adventure_camp")
PAGES = {
    "camp": {"title": "营地门牌", "subtitle": "每一段冒险，都从这里出发。", "symbol": "⌂"},
    "journey": {"title": "冒险地图", "subtitle": "看清方向，再迈出下一步。", "symbol": "◇"},
    "settings": {"title": "营地设置", "subtitle": "让营地成为适合你的地方。", "symbol": "⚙"},
    "quests": {"title": "主线任务", "subtitle": "让目标一步步清晰。", "symbol": "✧"},
    "tasks": {"title": "副本任务", "subtitle": "把下一步变成可以行动的小事。", "symbol": "▧"},
    "focus": {"title": "专注沙漏", "subtitle": "为当下留一段专注的时间。", "symbol": "⌛"},
    "journal": {"title": "历练手记", "subtitle": "让真实的行动留下痕迹。", "symbol": "✎"},
    "growth": {"title": "成长与奖励", "subtitle": "让每一步积累被看见。", "symbol": "✦"},
    "data": {"title": "数据与恢复", "subtitle": "导出与找回你的冒险记录。", "symbol": "▣"},
    "spirit-stones": {"title": "灵石区", "subtitle": "AI 能力中心", "symbol": "◆"},
    "account": {"title": "角色账号", "subtitle": "这里是你的冒险身份。", "symbol": "◉"},
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_level)
    database = Database(settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        logger.info("application_started")
        yield
        database.dispose()
        logger.info("application_stopped")

    app = FastAPI(title=settings.app_name, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.database = database
    app.state.settings = settings
    from app.modules.quests.router import router as quest_router
    app.include_router(quest_router)
    from app.modules.tasks.router import router as task_router
    app.include_router(task_router)
    from app.modules.activity.router import router as focus_router
    app.include_router(focus_router)
    from app.modules.activity.journal_router import router as journal_router
    app.include_router(journal_router)
    from app.modules.growth.router import router as growth_router
    app.include_router(growth_router)
    from app.modules.data_tools.router import router as data_router
    app.include_router(data_router)
    from app.modules.ai_gateway.router import router as ai_router
    app.include_router(ai_router)
    app.mount("/static", StaticFiles(directory=ROOT / "app/static"), name="static")
    templates = Jinja2Templates(directory=ROOT / "app/templates")

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = uuid4().hex
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception as error:
            logger.error("request_failed type=%s", type(error).__name__, extra={"request_id": request_id})
            response = JSONResponse({"error": "请求暂时无法完成", "request_id": request_id}, status_code=500)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        response.headers["Cache-Control"] = "no-store"
        logger.info("request_completed method=%s status=%s", request.method, response.status_code, extra={"request_id": request_id})
        return response

    @app.get("/health/live")
    def live():
        return {"status": "ok", "stage": "0"}

    @app.get("/health/ready")
    def ready():
        status = database.status()
        return JSONResponse({"status": status.state, "message": status.message}, status_code=200 if status.ready else 503)

    def render(request: Request, page: str):
        return templates.TemplateResponse(request=request, name="page.html", context={
            "pages": PAGES, "page": page, "current": PAGES[page],
            "app_name": settings.app_name, "timezone": settings.app_timezone,
            "database_configured": bool(settings.database_url),
        })

    @app.get("/", response_class=HTMLResponse)
    def camp(request: Request):
        if database.sessions is None:
            return render(request, "camp")
        from app.modules.identity.service import current_user
        from app.modules.dashboard.service import dashboard
        with database.transaction() as db:
            user = current_user(db, request.cookies.get("camp_session"))
            if not user:
                return render(request, "camp")
            data = dashboard(db, user)
            return templates.TemplateResponse(request=request, name="dashboard.html", context={
                "pages": PAGES, "page": "camp", "current": PAGES["camp"],
                "app_name": settings.app_name, "user": user, "data": data})

    @app.get("/journey", response_class=HTMLResponse)
    def journey(request: Request):
        return render(request, "journey")

    @app.get("/spirit-stones", response_class=HTMLResponse)
    def spirit_stones(request: Request):
        return templates.TemplateResponse(request=request, name="spirit_stones.html", context={"pages": PAGES, "page": "spirit-stones", "current": PAGES["spirit-stones"], "app_name": settings.app_name})

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        return render(request, "settings")

    return app


app = create_app()
