"""Remember the task selected in a startup coaching conversation."""
from alembic import op
import sqlalchemy as sa

revision = '0014_chat_target'
down_revision = '0013_recommendation_reliability'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('startup_conversations', sa.Column('selected_target_key', sa.String(48), nullable=True))


def downgrade():
    op.drop_column('startup_conversations', 'selected_target_key')
