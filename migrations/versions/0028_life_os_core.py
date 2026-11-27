"""Persistent originals and versioned life-os analyses; additive only."""
from alembic import op
import sqlalchemy as sa
revision='0028_life_os_core'
down_revision='0027_item_entitlements'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('life_os_messages',
        sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('user_id',sa.Uuid(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('request_id',sa.Uuid(),nullable=False),sa.Column('content',sa.String(4000),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.UniqueConstraint('user_id','request_id',name='uq_life_os_message_request'),sa.UniqueConstraint('id','user_id',name='uq_life_os_message_owner'))
    op.create_index('ix_life_os_messages_user_id','life_os_messages',['user_id'])
    op.create_table('life_os_analyses',
        sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('user_id',sa.Uuid(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('message_id',sa.Uuid(),nullable=False),sa.Column('request_id',sa.Uuid(),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),sa.Column('error_code',sa.String(50)),
        sa.Column('result',sa.JSON()),sa.Column('source_ids',sa.JSON(),nullable=False),sa.Column('prompt_version',sa.String(30),nullable=False),
        sa.Column('model_id',sa.String(160)),sa.Column('config_version',sa.Integer()),sa.Column('usage',sa.JSON()),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column('finished_at',sa.DateTime(timezone=True)),
        sa.UniqueConstraint('user_id','request_id',name='uq_life_os_analysis_request'),
        sa.ForeignKeyConstraint(['message_id','user_id'],['life_os_messages.id','life_os_messages.user_id']))
    op.create_index('ix_life_os_analyses_user_id','life_os_analyses',['user_id'])
    op.create_index('ix_life_os_analyses_message_id','life_os_analyses',['message_id'])

def downgrade():
    op.drop_table('life_os_analyses')
    op.drop_table('life_os_messages')
