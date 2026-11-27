"""Add owner-scoped quest history."""
from alembic import op
import sqlalchemy as sa

revision = "0003_quest_events"
down_revision = "0002_identity_quests"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("quest_events", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("main_quest_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(40), nullable=False), sa.Column("detail", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["main_quest_id", "user_id"], ["main_quests.id", "main_quests.user_id"], name="fk_event_quest_owner"))
    op.create_index("ix_quest_events_user_id", "quest_events", ["user_id"])
    op.create_index("ix_quest_events_main_quest_id", "quest_events", ["main_quest_id"])


def downgrade():
    op.drop_table("quest_events")
