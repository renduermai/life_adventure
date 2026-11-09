"""Tasks, completion history and idempotent commands."""
from alembic import op
import sqlalchemy as sa

revision = "0004_tasks"
down_revision = "0003_quest_events"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_milestone_id_quest_user", "milestones", ["id", "main_quest_id", "user_id"])
    op.create_table("tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("main_quest_id", sa.Uuid()), sa.Column("milestone_id", sa.Uuid()),
        sa.Column("parent_task_id", sa.Uuid()), sa.Column("recurrence_from_id", sa.Uuid(), unique=True),
        sa.Column("title", sa.String(160), nullable=False), sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(60), nullable=False), sa.Column("priority", sa.String(12), nullable=False),
        sa.Column("due_date", sa.Date()), sa.Column("status", sa.String(16), nullable=False),
        sa.Column("repeat_rule", sa.String(12), nullable=False),
        sa.Column("completion_round", sa.Integer(), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("id", "user_id", name="uq_task_id_user"),
        sa.ForeignKeyConstraint(["main_quest_id", "user_id"], ["main_quests.id", "main_quests.user_id"], name="fk_task_quest_owner"),
        sa.ForeignKeyConstraint(["milestone_id", "main_quest_id", "user_id"], ["milestones.id", "milestones.main_quest_id", "milestones.user_id"], name="fk_task_milestone_owner"),
        sa.ForeignKeyConstraint(["parent_task_id", "user_id"], ["tasks.id", "tasks.user_id"], name="fk_task_parent_owner"),
        sa.ForeignKeyConstraint(["recurrence_from_id", "user_id"], ["tasks.id", "tasks.user_id"], name="fk_task_recurrence_owner"),
        sa.CheckConstraint("status IN ('todo','in_progress','completed')", name="ck_task_status"),
        sa.CheckConstraint("priority IN ('low','normal','high')", name="ck_task_priority"),
        sa.CheckConstraint("repeat_rule IN ('none','daily','weekly','monthly')", name="ck_task_repeat"),
        sa.CheckConstraint("milestone_id IS NULL OR main_quest_id IS NOT NULL", name="ck_task_milestone_quest"),
        sa.CheckConstraint("parent_task_id IS NULL OR parent_task_id != id", name="ck_task_not_self"),
        sa.CheckConstraint("parent_task_id IS NULL OR repeat_rule = 'none'", name="ck_task_child_repeat"),
        sa.CheckConstraint("completion_round >= 0 AND version >= 1", name="ck_task_counters"),
        sa.CheckConstraint("(status = 'completed') = (completed_at IS NOT NULL)", name="ck_task_completed_at"))
    for column in ("user_id", "main_quest_id", "milestone_id", "parent_task_id"):
        op.create_index(f"ix_tasks_{column}", "tasks", [column])
    op.create_table("task_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False), sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("completion_round", sa.Integer(), nullable=False),
        sa.Column("reversal_of", sa.Uuid(), sa.ForeignKey("task_events.id"), unique=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["task_id", "user_id"], ["tasks.id", "tasks.user_id"], name="fk_task_event_owner"))
    for column in ("user_id", "task_id"):
        op.create_index(f"ix_task_events_{column}", "task_events", [column])
    op.create_index("uq_task_completion_event", "task_events", ["task_id", "completion_round", "kind"], unique=True,
                    postgresql_where=sa.text("kind IN ('completed','reopened')"))
    op.create_table("task_commands",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False), sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("result_task_id", sa.Uuid(), sa.ForeignKey("tasks.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "request_id", name="uq_task_command_request"))
    op.create_index("ix_task_commands_user_id", "task_commands", ["user_id"])


def downgrade():
    op.drop_table("task_commands")
    op.drop_table("task_events")
    op.drop_table("tasks")
    op.drop_constraint("uq_milestone_id_quest_user", "milestones", type_="unique")
