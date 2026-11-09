"""Owner-scoped quest and milestone operations."""
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.quests.models import MainQuest, Milestone


def validate_title(title: str) -> str:
    title = title.strip()
    if not 1 <= len(title) <= 160:
        raise ValueError("标题须为 1–160 个字符")
    return title


def date_value(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        raise ValueError("日期格式无效") from None


def get_quest(db: Session, user_id: UUID, quest_id: UUID, deleted: bool = False) -> MainQuest | None:
    return db.scalar(select(MainQuest).where(MainQuest.id == quest_id, MainQuest.user_id == user_id,
                     MainQuest.deleted_at.is_not(None) if deleted else MainQuest.deleted_at.is_(None)))


def get_milestone(db: Session, user_id: UUID, quest_id: UUID, milestone_id: UUID, deleted: bool = False) -> Milestone | None:
    return db.scalar(select(Milestone).where(Milestone.id == milestone_id, Milestone.user_id == user_id,
                     Milestone.main_quest_id == quest_id,
                     Milestone.deleted_at.is_not(None) if deleted else Milestone.deleted_at.is_(None)))


def set_quest_fields(quest: MainQuest, title: str, description: str, start: str, due: str) -> None:
    title = validate_title(title)
    if len(description) > 5000:
        raise ValueError("描述不能超过 5000 字")
    start_date, due_date = date_value(start), date_value(due)
    if start_date and due_date and due_date < start_date:
        raise ValueError("预计完成日期不能早于开始日期")
    quest.title, quest.description = title, description.strip()
    quest.start_date, quest.due_date = start_date, due_date


def set_milestone_fields(milestone: Milestone, title: str, description: str, due: str) -> None:
    title = validate_title(title)
    if len(description) > 5000:
        raise ValueError("描述不能超过 5000 字")
    milestone.title, milestone.description, milestone.due_date = title, description.strip(), date_value(due)


def soft_delete(record: MainQuest | Milestone) -> None:
    record.deleted_at = datetime.now(timezone.utc)


def progress(milestones: list[Milestone]) -> int | None:
    """Fallback progress when no live task leaves are associated."""
    if not milestones:
        return None
    return round(sum(m.status == "completed" for m in milestones) * 100 / len(milestones))


def quest_progress(db: Session, user_id: UUID, quest_id: UUID, milestones: list[Milestone]) -> dict:
    from app.modules.tasks.service import progress_counts
    completed, total = progress_counts(db, user_id, quest_id)
    if total:
        return {"progress": round(completed * 100 / total), "progress_label": f"已完成末级任务 {completed} / {total}"}
    return {"progress": progress([m for m in milestones if m.deleted_at is None]), "progress_label": "已完成里程碑 / 未删除里程碑"}
