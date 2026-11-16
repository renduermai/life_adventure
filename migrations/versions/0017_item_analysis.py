"""Independent item classification cache and safe attempt metadata."""
from alembic import op
import sqlalchemy as sa

revision = '0017_item_analysis'
down_revision = '0016_startup_items'
branch_labels = None
depends_on = None


def upgrade():
    for name, datatype in (
        ('analysis_result', sa.JSON()), ('analysis_fingerprint', sa.String(64)),
        ('analysis_config', sa.String(100)), ('analysis_error', sa.String(50)),
        ('analysis_attempt_id', sa.Uuid()), ('analysis_attempt_fingerprint', sa.String(64)),
        ('analysis_attempt_status', sa.String(20)), ('analysis_started_at', sa.DateTime(timezone=True))):
        op.add_column('startup_items', sa.Column(name, datatype, nullable=True))


def downgrade():
    for name in ('analysis_started_at', 'analysis_attempt_status', 'analysis_attempt_fingerprint',
                 'analysis_attempt_id', 'analysis_error', 'analysis_config', 'analysis_fingerprint', 'analysis_result'):
        op.drop_column('startup_items', name)
