from zoneinfo import ZoneInfo
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from app.core.config import ROOT
from app.modules.identity.service import current_user, lock_user
from app.modules.quests.router import back, same_origin
from app.modules.growth.models import RewardEntry, RewardSettings
from app.modules.growth.service import balances, level, settings, DEFAULT_XP, DEFAULT_COINS
from app.modules.tasks.models import Task

router = APIRouter()
templates = Jinja2Templates(directory=ROOT / 'app/templates')

def render(request, **kwargs):
    from app.main import PAGES
    return templates.TemplateResponse(request=request, name='growth.html', context={
        'app_name':request.app.state.settings.app_name, 'pages':PAGES, 'page':'growth', 'current':PAGES['growth'], **kwargs})

@router.get('/growth')
def growth_page(request: Request):
    with request.app.state.database.transaction() as db:
        user=current_user(db,request.cookies.get('camp_session'))
        if not user: return back('/account')
        xp, coins = balances(db,user.id)
        rule = db.get(RewardSettings,user.id)
        entries = list(db.scalars(select(RewardEntry).where(RewardEntry.user_id==user.id).order_by(RewardEntry.created_at.desc(),RewardEntry.id.desc())))
        tasks = {t.id:t.title for t in db.scalars(select(Task).where(Task.user_id==user.id))}
        running = 0
        transitions = {}
        for entry in reversed(entries):
            before = level(running)
            running += entry.xp_delta
            after = level(running)
            if before != after: transitions[entry.id] = (before, after)
        return render(request,xp=xp,coins=coins,level=level(xp),rule=rule,default_xp=DEFAULT_XP,default_coins=DEFAULT_COINS,entries=entries,tasks=tasks,transitions=transitions,zone=ZoneInfo(user.timezone))

def save_rules(request,form):
    try:
        xp=int(str(form.get('xp',''))); coins=int(str(form.get('coins','')))
        if not (0 <= xp <= 100000 and 0 <= coins <= 100000): raise ValueError('奖励数值须为 0–100000 的整数')
        with request.app.state.database.transaction() as db:
            user=current_user(db,request.cookies.get('camp_session'))
            if not user: return back('/account')
            lock_user(db,user.id)
            rule=settings(db,user.id)
            if (rule.xp_per_task,rule.coins_per_task)!=(xp,coins):
                rule.xp_per_task,rule.coins_per_task=xp,coins
                rule.rule_version += 1
            return back('/growth')
    except ValueError:
        return render(request,error='请输入 0–100000 之间的整数',xp=None,coins=None,level=None,rule=None,default_xp=DEFAULT_XP,default_coins=DEFAULT_COINS,entries=[],tasks={},transitions={},zone=ZoneInfo('UTC'))

@router.post('/growth/settings')
async def growth_settings(request:Request):
    same_origin(request)
    return await run_in_threadpool(save_rules,request,await request.form())
