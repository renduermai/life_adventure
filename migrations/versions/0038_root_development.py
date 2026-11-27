"""Store source-linked spirit root development snapshots."""

from alembic import op
import sqlalchemy as sa

revision = '0038_root_development'
down_revision = '0037_spirit_root'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('spirit_root_sources', sa.Column('development', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('spirit_root_sources', 'development')
