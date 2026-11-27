"""Store authenticated feature visits for the guide."""

from alembic import op
import sqlalchemy as sa

revision = '0036_feature_visits'
down_revision = '0035_memory_friends'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'feature_visits',
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('feature', sa.String(40), primary_key=True),
        sa.Column('visited_at', sa.DateTime(timezone=True), primary_key=True),
    )


def downgrade():
    op.drop_table('feature_visits')
