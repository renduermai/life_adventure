"""Independent startup items; no quest or task relationships."""
from alembic import op
import sqlalchemy as sa

revision = '0016_startup_items'
down_revision = '0015_manual_focus'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('startup_items',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('description', sa.String(2000), nullable=False),
        sa.Column('importance', sa.Integer(), nullable=False),
        sa.Column('urgency', sa.Integer(), nullable=False),
        sa.Column('progress', sa.String(2000), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('create_request_id', sa.Uuid(), nullable=False),
        sa.Column('create_fingerprint', sa.String(64), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'create_request_id', name='uq_startup_item_request'),
        sa.CheckConstraint('importance BETWEEN 0 AND 100', name='ck_startup_item_importance'),
        sa.CheckConstraint('urgency BETWEEN 0 AND 100', name='ck_startup_item_urgency'),
        sa.CheckConstraint('version >= 1', name='ck_startup_item_version'))
    op.create_index('ix_startup_items_user_id', 'startup_items', ['user_id'])


def downgrade():
    op.drop_table('startup_items')
