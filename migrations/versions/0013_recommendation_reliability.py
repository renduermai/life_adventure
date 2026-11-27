"""Record failed recommendation refreshes without losing prior published batches."""
from alembic import op
import sqlalchemy as sa

revision='0013_recommendation_reliability'
down_revision='0012_breakdown'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('recommendation_batches',sa.Column('error_code',sa.String(50),nullable=True))


def downgrade():
    op.drop_column('recommendation_batches','error_code')
