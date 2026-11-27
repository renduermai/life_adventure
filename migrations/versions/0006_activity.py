"""Versioned activity revisions and owner-scoped audit events."""
from alembic import op
import sqlalchemy as sa
revision = '0006_activity'
down_revision = '0005_focus'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('activity_logs', sa.Column('version', sa.Integer(), server_default='1', nullable=False))
    op.create_unique_constraint('uq_activity_id_user','activity_logs',['id','user_id'])
    op.create_table('activity_events',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('user_id',sa.Uuid(),sa.ForeignKey('users.id'),nullable=False),sa.Column('activity_id',sa.Uuid(),nullable=False),sa.Column('action',sa.String(16),nullable=False),sa.Column('payload',sa.JSON(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.ForeignKeyConstraint(['activity_id','user_id'],['activity_logs.id','activity_logs.user_id'],name='fk_activity_event_owner'))
    op.create_index('ix_activity_events_user_id','activity_events',['user_id'])
    op.create_index('ix_activity_events_activity_id','activity_events',['activity_id'])

def downgrade():
    op.drop_table('activity_events')
    op.drop_constraint('uq_activity_id_user','activity_logs',type_='unique')
    op.drop_column('activity_logs','version')
