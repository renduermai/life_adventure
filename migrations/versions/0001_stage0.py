"""Stage 0 baseline; no domain tables. Alembic manages its version table."""
revision = "0001_stage0"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
