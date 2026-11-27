"""Create focus sessions, segments, and activity records."""
from alembic import op
import sqlalchemy as sa
revision = '0005_focus'
down_revision = '0004_tasks'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('focus_sessions', sa.Column('id',sa.Uuid(),primary_key=True), sa.Column('user_id',sa.Uuid(),sa.ForeignKey('users.id'),nullable=False), sa.Column('task_id',sa.Uuid()), sa.Column('status',sa.String(16),nullable=False), sa.Column('mode',sa.String(16),nullable=False), sa.Column('target_seconds',sa.Integer()), sa.Column('accumulated_seconds',sa.Integer(),nullable=False), sa.Column('started_at',sa.DateTime(timezone=True),nullable=False), sa.Column('resumed_at',sa.DateTime(timezone=True)), sa.Column('ended_at',sa.DateTime(timezone=True)), sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False), sa.UniqueConstraint('id','user_id',name='uq_focus_id_user'), sa.ForeignKeyConstraint(['task_id','user_id'],['tasks.id','tasks.user_id'],name='fk_focus_task_owner'), sa.CheckConstraint("status IN ('running','paused','finished')",name='ck_focus_status'), sa.CheckConstraint("mode IN ('elapsed','countdown')",name='ck_focus_mode'), sa.CheckConstraint('accumulated_seconds >= 0 AND (target_seconds IS NULL OR target_seconds > 0)',name='ck_focus_seconds'))
    op.create_index('ix_focus_sessions_user_id','focus_sessions',['user_id'])
    op.create_index('uq_focus_active_user','focus_sessions',['user_id'],unique=True,postgresql_where=sa.text("status IN ('running','paused')"))
    op.create_table('focus_segments',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('user_id',sa.Uuid(),sa.ForeignKey('users.id'),nullable=False),sa.Column('session_id',sa.Uuid(),nullable=False),sa.Column('started_at',sa.DateTime(timezone=True),nullable=False),sa.Column('ended_at',sa.DateTime(timezone=True)),sa.ForeignKeyConstraint(['session_id','user_id'],['focus_sessions.id','focus_sessions.user_id'],name='fk_segment_session_owner'))
    op.create_index('ix_focus_segments_user_id','focus_segments',['user_id'])
    op.create_index('ix_focus_segments_session_id','focus_segments',['session_id'])
    op.create_table('activity_logs',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('user_id',sa.Uuid(),sa.ForeignKey('users.id'),nullable=False),sa.Column('task_id',sa.Uuid()),sa.Column('session_id',sa.Uuid()),sa.Column('occurred_at',sa.DateTime(timezone=True),nullable=False),sa.Column('duration_seconds',sa.Integer(),nullable=False),sa.Column('category',sa.String(60),nullable=False),sa.Column('note',sa.Text(),nullable=False),sa.Column('deleted_at',sa.DateTime(timezone=True)),sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.ForeignKeyConstraint(['task_id','user_id'],['tasks.id','tasks.user_id'],name='fk_activity_task_owner'),sa.ForeignKeyConstraint(['session_id','user_id'],['focus_sessions.id','focus_sessions.user_id'],name='fk_activity_session_owner'),sa.CheckConstraint('duration_seconds >= 0',name='ck_activity_duration'),sa.UniqueConstraint('session_id',name='uq_activity_session'))
    op.create_index('ix_activity_logs_user_id','activity_logs',['user_id'])

def downgrade():
    op.drop_table('activity_logs')
    op.drop_table('focus_segments')
    op.drop_table('focus_sessions')
