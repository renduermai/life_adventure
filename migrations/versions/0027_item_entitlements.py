"""Add expiry metadata without replacing existing items."""
from alembic import op
import sqlalchemy as sa

revision='0027_item_entitlements'
down_revision='0026_memory_wishes'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('memory_items',sa.Column('is_entitlement',sa.Boolean(),server_default=sa.text('false'),nullable=False))
    op.add_column('memory_items',sa.Column('expires_at',sa.Date(),nullable=True))
    op.create_check_constraint('ck_memory_item_entitlement','memory_items','(is_entitlement AND expires_at IS NOT NULL AND expires_at >= purchase_date) OR (NOT is_entitlement AND expires_at IS NULL)')

def downgrade():
    op.drop_constraint('ck_memory_item_entitlement','memory_items',type_='check')
    op.drop_column('memory_items','expires_at')
    op.drop_column('memory_items','is_entitlement')
