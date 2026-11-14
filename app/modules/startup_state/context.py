"""Read-only, owner-scoped context for the breakdown navigation placeholder."""
from sqlalchemy import select
from app.modules.quests.models import MainQuest, Milestone
from app.modules.quests.service import get_quest, quest_progress
from app.modules.tasks.service import get_task, ensure_available, children, TaskError
from app.modules.ai_gateway.security import AIError


def target_context(db, user_id, kind, target_id):
    if kind == 'quest':
        quest = get_quest(db, user_id, target_id)
        if not quest:
            raise AIError('not_found', '目标已删除或不可访问，请返回任务列表。', 404)
        milestones = list(db.scalars(select(Milestone).where(
            Milestone.user_id == user_id, Milestone.main_quest_id == quest.id,
            Milestone.deleted_at.is_(None))))
        value = quest_progress(db, user_id, quest.id, milestones)
        return {'kind': kind, 'id': str(quest.id), 'title': quest.title,
                'description': quest.description, 'main_quest': quest.title,
                'progress': value['progress'], 'status': quest.status,
                'href': '/quests/' + str(quest.id), 'steps': [m.title for m in milestones]}
    try:
        task = get_task(db, user_id, target_id)
        ensure_available(db, task)
    except TaskError:
        raise AIError('not_found', '目标已删除、关联不可用或无权访问，请返回任务列表。', 404) from None
    quest = get_quest(db, user_id, task.main_quest_id) if task.main_quest_id else None
    subtasks = children(db, task)
    progress = round(sum(t.status == 'completed' for t in subtasks) * 100 / len(subtasks)) if subtasks else (100 if task.status == 'completed' else 0)
    return {'kind': kind, 'id': str(task.id), 'title': task.title,
            'description': task.description, 'main_quest': quest.title if quest else '独立副本',
            'progress': progress, 'status': task.status, 'href': '/tasks/' + str(task.id),
            'steps': [t.title for t in subtasks]}
