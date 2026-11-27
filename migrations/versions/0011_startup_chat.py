"""Persistent startup conversations and confirmed advice provenance."""
from alembic import op
import sqlalchemy as sa

revision = '0011_startup_chat'
down_revision = '0010_recommendations'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('startup_conversations',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(60), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('id', 'user_id', name='uq_chat_owner'))
    op.create_index('ix_startup_conversations_user_id', 'startup_conversations', ['user_id'])
    op.create_table('startup_chat_turns',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('request_id', sa.Uuid(), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('base_generation', sa.Integer(), nullable=False),
        sa.Column('message', sa.String(2000), nullable=False),
        sa.Column('response', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('error_code', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('id', 'user_id', name='uq_chat_turn_owner'),
        sa.UniqueConstraint('user_id', 'request_id', name='uq_chat_request'),
        sa.UniqueConstraint('conversation_id', 'sequence', name='uq_chat_sequence'),
        sa.ForeignKeyConstraint(['conversation_id','user_id'], ['startup_conversations.id','startup_conversations.user_id'], name='fk_chat_conversation_owner'),
        sa.CheckConstraint("status IN ('pending','succeeded','failed')", name='ck_chat_status'))
    op.create_index('ix_startup_chat_turns_user_id', 'startup_chat_turns', ['user_id'])
    op.add_column('startup_state_snapshots', sa.Column('source_turn_id', sa.Uuid(), nullable=True))
    op.create_foreign_key('fk_state_chat_owner', 'startup_state_snapshots', 'startup_chat_turns', ['source_turn_id','user_id'], ['id','user_id'])


def downgrade():
    op.drop_constraint('fk_state_chat_owner', 'startup_state_snapshots', type_='foreignkey')
    op.drop_column('startup_state_snapshots', 'source_turn_id')
    op.drop_table('startup_chat_turns')
    op.drop_table('startup_conversations')
