"""Transactional task commands. Callers own commit/rollback; never commit here."""
import calendar
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.identity.service import lock_user
from app.modules.quests.models import MainQuest, Milestone
from app.modules.quests.service import date_value, validate_title
from app.modules.tasks.models import Task, TaskCommand, TaskEvent

STATUSES = {"todo": "待办", "in_progress": "进行中", "completed": "已完成"}
PRIORITIES = {"low": "低", "normal": "普通", "high": "高"}
REPEATS = {"none": "不重复", "daily": "每天", "weekly": "每周", "monthly": "每月"}
EVENTS = {"created": "创建任务", "edited": "修改任务", "completed": "完成任务", "reopened": "撤销完成", "status": "更新状态", "deleted": "删除任务", "restored": "恢复任务", "recurrence": "生成下一期"}


class TaskError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def identifier(value: str | UUID | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        raise TaskError("关联编号无效") from None


def next_due(current: date, rule: str) -> date:
    try:
        if rule == "daily":
            return current + timedelta(days=1)
        if rule == "weekly":
            return current + timedelta(days=7)
        if rule == "monthly":
            year, month = (current.year + 1, 1) if current.month == 12 else (current.year, current.month + 1)
            return date(year, month, min(current.day, calendar.monthrange(year, month)[1]))
    except (ValueError, OverflowError):
        raise TaskError("下一期日期超出支持范围") from None
    raise TaskError("重复规则无效")


def fields(data: dict) -> dict:
    title = validate_title(str(data.get("title", "")))
    description, category = str(data.get("description", "")).strip(), str(data.get("category", "")).strip()
    priority, repeat = str(data.get("priority", "normal")), str(data.get("repeat_rule", "none"))
    if len(description) > 5000 or len(category) > 60:
        raise TaskError("描述最多 5000 字，分类最多 60 字")
    if priority not in PRIORITIES or repeat not in REPEATS:
        raise TaskError("优先级或重复规则无效")
    return dict(title=title, description=description, category=category, priority=priority,
                repeat_rule=repeat, due_date=date_value(str(data.get("due_date", ""))),
                main_quest_id=identifier(data.get("main_quest_id")), milestone_id=identifier(data.get("milestone_id")))


def get_task(db: Session, user_id: UUID, task_id: UUID) -> Task:
    task = db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user_id).execution_options(populate_existing=True))
    if task is None:
        raise TaskError("任务不存在或无权访问", 404)
    return task


def validate_links(db: Session, user_id: UUID, values: dict) -> None:
    quest_id, milestone_id = values["main_quest_id"], values["milestone_id"]
    if quest_id:
        quest = db.scalar(select(MainQuest).where(MainQuest.id == quest_id, MainQuest.user_id == user_id))
        if not quest or quest.deleted_at:
            raise TaskError("关联主线不可用，请先恢复主线或重新选择")
        if quest.status == "archived":
            raise TaskError("主线已归档，请先恢复为可用状态")
    if milestone_id:
        milestone = db.scalar(select(Milestone).where(Milestone.id == milestone_id,
                            Milestone.main_quest_id == quest_id, Milestone.user_id == user_id))
        if not milestone or milestone.deleted_at:
            raise TaskError("里程碑不可用，或不属于所选主线")


def children(db: Session, task: Task, include_deleted: bool = False) -> list[Task]:
    query = select(Task).where(Task.user_id == task.user_id, Task.parent_task_id == task.id)
    if not include_deleted:
        query = query.where(Task.deleted_at.is_(None))
    return list(db.scalars(query.order_by(Task.created_at, Task.id)))


def ensure_available(db: Session, task: Task) -> None:
    if task.deleted_at:
        raise TaskError("任务已删除，请先恢复")
    validate_links(db, task.user_id, {"main_quest_id": task.main_quest_id, "milestone_id": task.milestone_id})
    if task.parent_task_id:
        parent = get_task(db, task.user_id, task.parent_task_id)
        if parent.deleted_at:
            raise TaskError("请先恢复父任务")


def snapshot(task: Task) -> dict:
    return {key: str(value) if isinstance(value, (UUID, date, datetime)) else value for key in
            ("title", "description", "category", "priority", "due_date", "main_quest_id", "milestone_id", "parent_task_id", "status", "repeat_rule")
            for value in [getattr(task, key)]}


def event(db: Session, task: Task, kind: str, payload: dict | None = None, reversal_of: UUID | None = None) -> TaskEvent:
    record = TaskEvent(id=uuid4(), user_id=task.user_id, task_id=task.id, kind=kind,
                       completion_round=task.completion_round, payload=payload or {}, reversal_of=reversal_of,
                       created_at=datetime.now(timezone.utc))
    db.add(record)
    return record


def reopen(db: Session, task: Task, target: str = "todo") -> None:
    completion = db.scalar(select(TaskEvent).where(TaskEvent.task_id == task.id, TaskEvent.user_id == task.user_id,
                         TaskEvent.kind == "completed", TaskEvent.completion_round == task.completion_round))
    if completion is None:
        raise TaskError("完成记录缺失，请联系维护者", 409)
    task.status, task.completed_at = target, None
    reversal = event(db, task, "reopened", {"status": target}, completion.id)
    db.flush()
    from app.modules.growth.service import reverse
    reverse(db, task, completion, reversal)


def reopen_parent(db: Session, task: Task) -> None:
    if task.parent_task_id:
        parent = get_task(db, task.user_id, task.parent_task_id)
        if parent.status == "completed":
            reopen(db, parent)
            parent.version += 1


def create_task(db: Session, user_id: UUID, data: dict) -> Task:
    values = fields(data)
    parent_id = identifier(data.get("parent_task_id"))
    if parent_id:
        parent = get_task(db, user_id, parent_id)
        ensure_available(db, parent)
        if parent.parent_task_id:
            raise TaskError("当前支持一层子任务，请将更细的步骤写在描述中")
        if parent.repeat_rule != "none":
            raise TaskError("重复任务暂不支持子任务，请创建独立任务")
        if parent.status == "completed":
            raise TaskError("请先撤销父任务完成，再添加子任务")
        if values["repeat_rule"] != "none":
            raise TaskError("子任务不能单独重复")
        values.update(main_quest_id=parent.main_quest_id, milestone_id=parent.milestone_id)
    validate_links(db, user_id, values)
    task = Task(id=uuid4(), user_id=user_id, parent_task_id=parent_id, status="todo", completion_round=0, version=1, **values)
    db.add(task)
    db.flush()
    event(db, task, "created", snapshot(task))
    return task


def edit_task(db: Session, task: Task, data: dict) -> None:
    if task.deleted_at:
        raise TaskError("请先恢复任务再编辑")
    values = fields(data)
    all_children = children(db, task, include_deleted=True)
    if values["repeat_rule"] != "none" and all_children:
        raise TaskError("有子任务的任务不能设置重复")
    if task.parent_task_id:
        parent = get_task(db, task.user_id, task.parent_task_id)
        ensure_available(db, parent)
        if values["repeat_rule"] != "none":
            raise TaskError("子任务不能单独重复")
        values.update(main_quest_id=parent.main_quest_id, milestone_id=parent.milestone_id)
    validate_links(db, task.user_id, values)
    before = snapshot(task)
    for key, value in values.items():
        setattr(task, key, value)
    # Parent links are immutable; children inherit association edits in this transaction.
    for child in all_children:
        if (child.main_quest_id, child.milestone_id) != (task.main_quest_id, task.milestone_id):
            child.main_quest_id, child.milestone_id = task.main_quest_id, task.milestone_id
            child.version += 1
            event(db, child, "edited", {"inherited_from": str(task.id), "after": snapshot(child)})
    event(db, task, "edited", {"before": before, "after": snapshot(task)})


def generate_next(db: Session, task: Task, timezone_name: str) -> None:
    if task.repeat_rule == "none" or db.scalar(select(Task.id).where(Task.recurrence_from_id == task.id)):
        return
    anchor = task.due_date or datetime.now(ZoneInfo(timezone_name)).date()
    successor = Task(id=uuid4(), user_id=task.user_id, title=task.title, description=task.description,
                     category=task.category, priority=task.priority, due_date=next_due(anchor, task.repeat_rule),
                     main_quest_id=task.main_quest_id, milestone_id=task.milestone_id,
                     repeat_rule=task.repeat_rule, recurrence_from_id=task.id, status="todo", completion_round=0, version=1)
    db.add(successor)
    db.flush()
    event(db, successor, "created", {"previous_task_id": str(task.id), "after": snapshot(successor)})
    event(db, task, "recurrence", {"next_task_id": str(successor.id)})


def change_task(db: Session, task: Task, action: str, data: dict, timezone_name: str) -> None:
    if action == "edit":
        edit_task(db, task, data)
    elif action == "delete":
        if task.deleted_at:
            return
        task.deleted_at = datetime.now(timezone.utc)
        event(db, task, "deleted")
    elif action == "restore":
        if not task.deleted_at:
            return
        validate_links(db, task.user_id, {"main_quest_id": task.main_quest_id, "milestone_id": task.milestone_id})
        if task.parent_task_id and get_task(db, task.user_id, task.parent_task_id).deleted_at:
            raise TaskError("请先恢复父任务")
        task.deleted_at = None
        if task.status != "completed":
            reopen_parent(db, task)
        event(db, task, "restored")
    elif action == "status":
        ensure_available(db, task)
        target = str(data.get("status", ""))
        if target not in STATUSES:
            raise TaskError("任务状态无效")
        if target == task.status:
            return
        if target == "completed":
            if any(child.status != "completed" for child in children(db, task)):
                raise TaskError("请先完成全部未删除的子任务")
            task.status, task.completed_at = target, datetime.now(timezone.utc)
            task.completion_round += 1
            completion = event(db, task, "completed", snapshot(task))
            db.flush()
            from app.modules.growth.service import grant
            grant(db, task, completion)
            generate_next(db, task, timezone_name)
        else:
            if task.status == "completed":
                reopen(db, task, target)
            else:
                task.status = target
                event(db, task, "status", {"status": target})
            reopen_parent(db, task)
    else:
        raise TaskError("操作不存在", 404)
    task.version += 1
    db.flush()


def execute(db: Session, user_id: UUID, request_id: UUID, action: str, data: dict,
            task_ids: list[UUID] | None = None, versions: dict[str, int] | None = None) -> UUID | None:
    """Idempotent command + optimistic version + owner lock; batch is all-or-nothing."""
    user = lock_user(db, user_id)
    ids = sorted(set(task_ids or []), key=str)
    fingerprint = hashlib.sha256(json.dumps({"action": action, "data": data, "ids": [str(i) for i in ids],
                                            "versions": versions}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    old = db.scalar(select(TaskCommand).where(TaskCommand.user_id == user_id, TaskCommand.request_id == request_id))
    if old:
        if old.fingerprint != fingerprint:
            raise TaskError("该提交编号已用于其他操作，请刷新页面", 409)
        return old.result_task_id
    if action == "create":
        result_id = create_task(db, user_id, data).id
    else:
        if not 1 <= len(ids) <= 100:
            raise TaskError("请选中 1–100 个任务")
        if action == "edit" and len(ids) != 1:
            raise TaskError("每次只能编辑一个任务")
        tasks = [get_task(db, user_id, task_id) for task_id in ids]
        for task in tasks:
            if versions is None or versions.get(str(task.id)) != task.version:
                raise TaskError("任务已被修改，请刷新页面后再操作", 409)
        # Complete/delete children before parents; restore parents first.
        tasks.sort(key=lambda t: (bool(t.parent_task_id) if action == "restore" else not bool(t.parent_task_id), str(t.id)))
        for task in tasks:
            change_task(db, task, action, data, user.timezone)
        result_id = ids[0] if len(ids) == 1 else None
    db.add(TaskCommand(user_id=user_id, request_id=request_id, fingerprint=fingerprint, result_task_id=result_id))
    db.flush()
    return result_id


def progress_counts(db: Session, user_id: UUID, quest_id: UUID) -> tuple[int, int]:
    """Live leaves only. Deleted milestones/parents hide their descendants."""
    tasks = list(db.scalars(select(Task).where(Task.user_id == user_id, Task.main_quest_id == quest_id, Task.deleted_at.is_(None))))
    active_milestones = set(db.scalars(select(Milestone.id).where(Milestone.user_id == user_id,
                                Milestone.main_quest_id == quest_id, Milestone.deleted_at.is_(None))))
    root_ids = {t.id for t in tasks if t.parent_task_id is None}
    live = [t for t in tasks if (not t.milestone_id or t.milestone_id in active_milestones)
            and (not t.parent_task_id or t.parent_task_id in root_ids)]
    parents = {t.parent_task_id for t in live if t.parent_task_id}
    leaves = [t for t in live if t.id not in parents]
    return sum(t.status == "completed" for t in leaves), len(leaves)


def list_tasks(db: Session, user_id: UUID, *, status: str = "", category: str = "", quest_id: UUID | None = None,
               deleted: bool = False) -> list[Task]:
    query = select(Task).where(Task.user_id == user_id, Task.deleted_at.is_not(None) if deleted else Task.deleted_at.is_(None))
    if status:
        if status not in STATUSES:
            raise TaskError("筛选状态无效")
        query = query.where(Task.status == status)
    if category:
        query = query.where(Task.category == category)
    if quest_id:
        query = query.where(Task.main_quest_id == quest_id)
    return list(db.scalars(query.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc(), Task.id)))


def unavailable_reasons(db: Session, user_id: UUID, tasks: list[Task]) -> dict[UUID, str]:
    """Batch lookup so the list can explain blocked associations without N+1 queries."""
    quests = {q.id: q for q in db.scalars(select(MainQuest).where(MainQuest.user_id == user_id))}
    milestones = {m.id: m for m in db.scalars(select(Milestone).where(Milestone.user_id == user_id))}
    parent_ids = {t.parent_task_id for t in tasks if t.parent_task_id}
    parents = {t.id: t for t in db.scalars(select(Task).where(Task.user_id == user_id, Task.id.in_(parent_ids)))}
    reasons = {}
    for task in tasks:
        quest, milestone, parent = quests.get(task.main_quest_id), milestones.get(task.milestone_id), parents.get(task.parent_task_id)
        if quest and quest.deleted_at:
            reasons[task.id] = "关联主线已删除"
        elif quest and quest.status == "archived":
            reasons[task.id] = "关联主线已归档"
        elif milestone and milestone.deleted_at:
            reasons[task.id] = "关联里程碑已删除"
        elif parent and parent.deleted_at:
            reasons[task.id] = "父任务已删除"
    return reasons
