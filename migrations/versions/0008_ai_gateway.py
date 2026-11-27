"""AI configuration, bindings and credential-free invocation metadata."""
from alembic import op
import sqlalchemy as sa
revision = '0008_ai_gateway'
down_revision = '0007_rewards'
branch_labels = None
depends_on = None

def upgrade():
    # Explicit schema; no runtime model imports.
    op.create_table('ai_configs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('create_request_id', sa.Uuid(), nullable=False),
    sa.Column('create_fingerprint', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('base_url', sa.String(length=500), nullable=False),
    sa.Column('model_id', sa.String(length=160), nullable=False),
    sa.Column('protocol', sa.String(length=32), nullable=False),
    sa.Column('encrypted_key', sa.Text(), nullable=True),
    sa.Column('key_version', sa.String(length=16), nullable=False),
    sa.Column('key_mask', sa.String(length=16), nullable=False),
    sa.Column('expires_on', sa.Date(), nullable=True),
    sa.Column('notes', sa.String(length=2000), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('config_version', sa.Integer(), nullable=False),
    sa.Column('last_test_version', sa.Integer(), nullable=True),
    sa.Column('last_test_result', sa.String(length=40), nullable=True),
    sa.Column('last_test_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("protocol = 'openai_compatible'", name='ck_ai_protocol'),
    sa.CheckConstraint('NOT is_default OR (enabled AND deleted_at IS NULL)', name='ck_ai_default_enabled'),
    sa.CheckConstraint('config_version >= 1', name='ck_ai_config_version'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'user_id', name='uq_ai_config_owner'),
    sa.UniqueConstraint('user_id', 'create_request_id', name='uq_ai_config_request')
    )
    op.create_index('uq_ai_default', 'ai_configs', ['user_id'], unique=True, postgresql_where=sa.text('is_default'))
    op.create_index(op.f('ix_ai_configs_user_id'), 'ai_configs', ['user_id'], unique=False)
    op.create_table('ai_module_bindings',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('module_key', sa.String(length=40), nullable=False),
    sa.Column('config_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['config_id', 'user_id'], ['ai_configs.id', 'ai_configs.user_id'], name='fk_ai_binding_owner'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id', 'module_key')
    )
    op.create_table('ai_call_logs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('config_id', sa.Uuid(), nullable=False),
    sa.Column('config_version', sa.Integer(), nullable=False),
    sa.Column('model_id', sa.String(length=160), nullable=False),
    sa.Column('purpose', sa.String(length=40), nullable=False),
    sa.Column('request_id', sa.Uuid(), nullable=False),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('error_code', sa.String(length=40), nullable=True),
    sa.Column('usage', sa.JSON(), nullable=True),
    sa.Column('elapsed_ms', sa.Integer(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('running','succeeded','failed','unknown')", name='ck_ai_call_status'),
    sa.ForeignKeyConstraint(['config_id', 'user_id'], ['ai_configs.id', 'ai_configs.user_id'], name='fk_ai_call_owner'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'purpose', 'request_id', name='uq_ai_call_request')
    )
    op.create_index(op.f('ix_ai_call_logs_user_id'), 'ai_call_logs', ['user_id'], unique=False)

def downgrade():
    op.drop_table('ai_call_logs')
    op.drop_table('ai_module_bindings')
    op.drop_table('ai_configs')
