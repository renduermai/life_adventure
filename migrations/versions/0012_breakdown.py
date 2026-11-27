"""User-confirmed breakdown drafts, task mappings and checklists."""
from alembic import op
import sqlalchemy as sa
revision='0012_breakdown'
down_revision='0011_startup_chat'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('breakdown_plans',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('user_id',sa.Uuid(),sa.ForeignKey('users.id'),nullable=False),
        *[sa.Column(n,sa.Uuid(),nullable=True) for n in ['quest_id','task_id','snapshot_id','previous_id']],
        sa.Column('request_id',sa.Uuid(),nullable=False),
        *[sa.Column(n,sa.String(64),nullable=False) for n in ['request_fingerprint','context_fingerprint']],
        sa.Column('context',sa.JSON(),nullable=False),
        sa.Column('feedback',sa.String(2000),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('advice',sa.JSON(),nullable=True),
        sa.Column('model_info',sa.JSON(),nullable=True),
        sa.Column('error_code',sa.String(50),nullable=True),
        sa.Column('confirmed_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('confirmation_fingerprint',sa.String(64),nullable=True),
        sa.Column('save_mode',sa.String(20),nullable=True),
        *[sa.Column(n,sa.JSON(),nullable=False) for n in ['mapping','execution','checklist']],
        sa.Column('checklist_version',sa.Integer(),nullable=False),
        sa.Column('checklist_events',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.UniqueConstraint('id','user_id',name='uq_breakdown_owner'),
        sa.UniqueConstraint('user_id','request_id',name='uq_breakdown_request'),
        sa.ForeignKeyConstraint(['quest_id','user_id'],['main_quests.id','main_quests.user_id'],name='fk_breakdown_quest'),
        sa.ForeignKeyConstraint(['task_id','user_id'],['tasks.id','tasks.user_id'],name='fk_breakdown_task'),
        sa.ForeignKeyConstraint(['snapshot_id','user_id'],['startup_state_snapshots.id','startup_state_snapshots.user_id'],name='fk_breakdown_state'),
        sa.ForeignKeyConstraint(['previous_id','user_id'],['breakdown_plans.id','breakdown_plans.user_id'],name='fk_breakdown_previous'),
        sa.CheckConstraint('(quest_id IS NULL) != (task_id IS NULL)',name='ck_breakdown_target'),
        sa.CheckConstraint("status IN ('generating','draft','confirmed','failed','superseded')",name='ck_breakdown_status'))
    op.create_index('ix_breakdown_plans_user_id','breakdown_plans',['user_id'])
    op.add_column('startup_state_snapshots',sa.Column('source_plan_id',sa.Uuid(),nullable=True))
    op.create_foreign_key('fk_state_breakdown_owner','startup_state_snapshots','breakdown_plans',['source_plan_id','user_id'],['id','user_id'])


def downgrade():
    op.drop_constraint('fk_state_breakdown_owner','startup_state_snapshots',type_='foreignkey')
    op.drop_column('startup_state_snapshots','source_plan_id')
    op.drop_table('breakdown_plans')
