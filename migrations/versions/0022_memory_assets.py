"""Private cloud image assets and immutable object lifecycle."""
from alembic import op
import sqlalchemy as sa

revision = '0022_memory_assets'
down_revision = '0021_library_copies'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('memory_assets',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('create_request_id', sa.Uuid(), nullable=False),
        sa.Column('create_fingerprint', sa.String(64), nullable=False),
        sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('id', 'user_id', name='uq_memory_asset_owner'),
        sa.UniqueConstraint('user_id', 'create_request_id', name='uq_memory_asset_request'),
        sa.CheckConstraint('version >= 1', name='ck_memory_asset_version'))
    op.create_table('memory_asset_objects',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('asset_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('request_id', sa.Uuid(), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('bucket', sa.String(63), nullable=False),
        sa.Column('object_path', sa.String(100), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('byte_size', sa.Integer(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('content_type', sa.String(32), nullable=False),
        sa.Column('state', sa.String(12), nullable=False),
        sa.Column('error_code', sa.String(40)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('delete_after', sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(['asset_id', 'user_id'], ['memory_assets.id', 'memory_assets.user_id'], name='fk_memory_object_owner'),
        sa.UniqueConstraint('user_id', 'request_id', name='uq_memory_object_request'),
        sa.UniqueConstraint('bucket', 'object_path', name='uq_memory_object_key'),
        sa.CheckConstraint("state IN ('pending','active','retired','deleted')", name='ck_memory_object_state'),
        sa.CheckConstraint('byte_size BETWEEN 1 AND 5242880 AND width > 0 AND height > 0 AND width * height <= 12000000', name='ck_memory_object_size'),
        sa.CheckConstraint("content_type = 'image/webp'", name='ck_memory_object_type'))
    op.create_index('uq_memory_object_active', 'memory_asset_objects', ['asset_id'], unique=True, postgresql_where=sa.text("state = 'active'"))
    op.create_index('ix_memory_object_cleanup', 'memory_asset_objects', ['state', 'delete_after'])


def downgrade():
    op.drop_table('memory_asset_objects')
    op.drop_table('memory_assets')
