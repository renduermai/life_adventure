"""Reward commands share the task transaction; callers own commit."""
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy import func, select
from app.modules.growth.models import RewardEntry, RewardSettings
from app.modules.tasks.models import Task, TaskEvent

DEFAULT_XP = 10
DEFAULT_COINS = 5
LEVEL_STEP = 100


def level(xp: int) -> int:
    return max(0, xp) // LEVEL_STEP + 1


def settings(db, user_id):
    result = db.get(RewardSettings, user_id)
    if result is None:
        result = RewardSettings(user_id=user_id, xp_per_task=DEFAULT_XP, coins_per_task=DEFAULT_COINS, rule_version=1)
        db.add(result)
        db.flush()
    return result


def grant(db, task, completed_event):
    existing = db.scalar(select(RewardEntry).where(RewardEntry.source_event_id == completed_event.id))
    if existing:
        return existing
    rule = settings(db, task.user_id)
    entry = RewardEntry(id=uuid4(), user_id=task.user_id, task_id=task.id, source_event_id=completed_event.id,
                        kind='grant', xp_delta=rule.xp_per_task, coin_delta=rule.coins_per_task, rule_version=rule.rule_version, created_at=datetime.now(timezone.utc))
    db.add(entry)
    return entry


def reverse(db, task, completion, reversal_event):
    original = db.scalar(select(RewardEntry).where(RewardEntry.user_id == task.user_id,
                         RewardEntry.source_event_id == completion.id, RewardEntry.kind == 'grant'))
    if original is None:
        return None
    existing = db.scalar(select(RewardEntry).where(RewardEntry.reversal_of == original.id))
    if existing:
        return existing
    entry = RewardEntry(id=uuid4(), user_id=task.user_id, task_id=task.id, source_event_id=reversal_event.id,
                        reversal_of=original.id, kind='reversal', xp_delta=-original.xp_delta,
                        coin_delta=-original.coin_delta, rule_version=original.rule_version, created_at=datetime.now(timezone.utc))
    db.add(entry)
    return entry


def balances(db, user_id):
    row = db.execute(select(func.coalesce(func.sum(RewardEntry.xp_delta),0), func.coalesce(func.sum(RewardEntry.coin_delta),0)).where(RewardEntry.user_id == user_id)).one()
    return int(row[0]), int(row[1])


def backfill_current(db, user_id):
    """One grant per currently completed task, keyed by latest completion event."""
    tasks = list(db.scalars(select(Task).where(Task.user_id == user_id, Task.status == 'completed')))
    for task in tasks:
        completion = db.scalar(select(TaskEvent).where(TaskEvent.user_id == user_id, TaskEvent.task_id == task.id,
                               TaskEvent.kind == 'completed', TaskEvent.completion_round == task.completion_round))
        if completion is None:
            raise ValueError('历史完成记录缺失，补发已回滚')
        grant(db, task, completion)
        db.flush()
    return len(tasks)
