"""Reward rules and append-only reward ledger."""
from alembic import op
import sqlalchemy as sa
revision = '0007_rewards'
down_revision = '0006_activity'
branch_labels = None
depends_on = None

def upgrade():
    op.create_unique_constraint('uq_task_event_id_user','task_events',['id','user_id'])
    op.create_table('reward_settings',sa.Column('user_id',sa.Uuid(),sa.ForeignKey('users.id'),primary_key=True),sa.Column('xp_per_task',sa.Integer(),nullable=False),sa.Column('coins_per_task',sa.Integer(),nullable=False),sa.Column('rule_version',sa.Integer(),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.CheckConstraint('xp_per_task >= 0 AND coins_per_task >= 0',name='ck_reward_nonnegative'))
    op.create_table('reward_entries',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('user_id',sa.Uuid(),sa.ForeignKey('users.id'),nullable=False),sa.Column('task_id',sa.Uuid(),nullable=False),sa.Column('source_event_id',sa.Uuid(),nullable=False),sa.Column('reversal_of',sa.Uuid()),sa.Column('kind',sa.String(16),nullable=False),sa.Column('xp_delta',sa.Integer(),nullable=False),sa.Column('coin_delta',sa.Integer(),nullable=False),sa.Column('rule_version',sa.Integer(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.ForeignKeyConstraint(['task_id','user_id'],['tasks.id','tasks.user_id'],name='fk_reward_task_owner'),sa.ForeignKeyConstraint(['source_event_id','user_id'],['task_events.id','task_events.user_id'],name='fk_reward_event_owner'),sa.ForeignKeyConstraint(['reversal_of','user_id'],['reward_entries.id','reward_entries.user_id'],name='fk_reward_reversal_owner'),sa.UniqueConstraint('id','user_id',name='uq_reward_id_user'),sa.UniqueConstraint('source_event_id',name='uq_reward_source_event'),sa.UniqueConstraint('reversal_of',name='uq_reward_reversal'),sa.CheckConstraint("kind IN ('grant','reversal')",name='ck_reward_kind'),sa.CheckConstraint("(kind='grant' AND reversal_of IS NULL AND xp_delta >= 0 AND coin_delta >= 0) OR (kind='reversal' AND reversal_of IS NOT NULL AND xp_delta <= 0 AND coin_delta <= 0)",name='ck_reward_deltas'))
    op.create_index('ix_reward_entries_user_id','reward_entries',['user_id'])
    op.create_index('ix_reward_entries_task_id','reward_entries',['task_id'])
    # Backfill exactly the currently completed rounds, including soft-deleted tasks.
    # Abort the entire transaction if historical facts are inconsistent.
    op.execute("""DO $$ BEGIN IF EXISTS (
      SELECT 1 FROM tasks t WHERE t.status = 'completed' AND NOT EXISTS (
        SELECT 1 FROM task_events e WHERE e.task_id=t.id AND e.user_id=t.user_id
        AND e.kind='completed' AND e.completion_round=t.completion_round))
      THEN RAISE EXCEPTION 'completed task missing completion event'; END IF; END $$""")
    op.execute("""INSERT INTO reward_settings (user_id,xp_per_task,coins_per_task,rule_version)
      SELECT id,10,5,1 FROM users""")
    op.execute("""INSERT INTO reward_entries (id,user_id,task_id,source_event_id,kind,xp_delta,coin_delta,rule_version)
      SELECT gen_random_uuid(),t.user_id,t.id,e.id,'grant',10,5,1
      FROM tasks t JOIN task_events e ON e.task_id=t.id AND e.user_id=t.user_id
        AND e.kind='completed' AND e.completion_round=t.completion_round
      WHERE t.status='completed'""")

def downgrade():
    op.drop_table('reward_entries')
    op.drop_table('reward_settings')
    op.drop_constraint('uq_task_event_id_user','task_events',type_='unique')
