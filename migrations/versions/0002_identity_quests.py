"""Create identity, main quest, and milestone tables."""
from alembic import op
import sqlalchemy as sa

revision = "0002_identity_quests"
down_revision = "0001_stage0"
branch_labels = None
depends_on = None


def timestamps():
    return [sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def upgrade():
    op.create_table("users", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False), *timestamps())
    op.create_table("login_sessions", sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_login_sessions_user_id", "login_sessions", ["user_id"])
    op.create_table("main_quests", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(160), nullable=False), sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False), sa.Column("start_date", sa.Date()),
        sa.Column("due_date", sa.Date()), sa.Column("deleted_at", sa.DateTime(timezone=True)), *timestamps(),
        sa.UniqueConstraint("id", "user_id", name="uq_quest_id_user"),
        sa.CheckConstraint("status IN ('active','paused','completed','archived')", name="ck_quest_status"),
        sa.CheckConstraint("due_date IS NULL OR start_date IS NULL OR due_date >= start_date", name="ck_quest_dates"))
    op.create_index("ix_main_quests_user_id", "main_quests", ["user_id"])
    op.create_table("milestones", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("main_quest_id", sa.Uuid(), nullable=False), sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False), sa.Column("status", sa.String(16), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False), sa.Column("due_date", sa.Date()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)), *timestamps(),
        sa.ForeignKeyConstraint(["main_quest_id", "user_id"], ["main_quests.id", "main_quests.user_id"], name="fk_milestone_quest_owner"),
        sa.CheckConstraint("status IN ('pending','completed')", name="ck_milestone_status"))
    op.create_index("ix_milestones_user_id", "milestones", ["user_id"])
    op.create_index("ix_milestones_main_quest_id", "milestones", ["main_quest_id"])


def downgrade():
    op.drop_table("milestones")
    op.drop_table("main_quests")
    op.drop_table("login_sessions")
    op.drop_table("users")
