"""Versioned derived classifications; originals are never overwritten."""
from alembic import op
import sqlalchemy as sa
revision = '0019_distraction_classification'
down_revision = '0018_distraction_notes'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('distraction_classification_runs',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('user_id',sa.Uuid(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('request_id',sa.Uuid(),nullable=False),
        sa.Column('fingerprint',sa.String(64),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('error_code',sa.String(40)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.UniqueConstraint('user_id','request_id',name='uq_distraction_run_request'),
        sa.UniqueConstraint('id','user_id',name='uq_distraction_run_owner'))
    op.create_index('ix_distraction_classification_runs_user_id','distraction_classification_runs',['user_id'])
    op.create_table('distraction_topics',
        sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('run_id',sa.Uuid(),nullable=False),
        sa.Column('user_id',sa.Uuid(),nullable=False),sa.Column('category',sa.String(80),nullable=False),
        sa.Column('summary',sa.String(300),nullable=False),
        sa.ForeignKeyConstraint(['run_id','user_id'],['distraction_classification_runs.id','distraction_classification_runs.user_id']),
        sa.UniqueConstraint('id','run_id','user_id',name='uq_distraction_topic_owner'))
    op.create_table('distraction_memberships',
        sa.Column('run_id',sa.Uuid(),primary_key=True),sa.Column('note_id',sa.Uuid(),primary_key=True),
        sa.Column('user_id',sa.Uuid(),nullable=False),sa.Column('topic_id',sa.Uuid()),
        sa.ForeignKeyConstraint(['run_id','user_id'],['distraction_classification_runs.id','distraction_classification_runs.user_id']),
        sa.ForeignKeyConstraint(['note_id','user_id'],['distraction_notes.id','distraction_notes.user_id']),
        sa.ForeignKeyConstraint(['topic_id','run_id','user_id'],['distraction_topics.id','distraction_topics.run_id','distraction_topics.user_id']))


def downgrade():
    op.drop_table('distraction_memberships')
    op.drop_table('distraction_topics')
    op.drop_table('distraction_classification_runs')
