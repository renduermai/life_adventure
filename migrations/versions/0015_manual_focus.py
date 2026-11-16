"""Independent manual focus labels on quests and tasks."""
from alembic import op
import sqlalchemy as sa
revision = '0015_manual_focus'
down_revision = '0014_chat_target'
branch_labels = None
depends_on = None

def upgrade():
    for table in ('main_quests', 'tasks'):
        prefix = 'quests' if table == 'main_quests' else 'tasks'
        op.add_column(table, sa.Column('manual_focus_status', sa.String(24), nullable=False, server_default='normal'))
        op.add_column(table, sa.Column('manual_focus_version', sa.Integer(), nullable=False, server_default=sa.text('1')))
        op.create_check_constraint('ck_'+prefix+'_manual_focus', table, "manual_focus_status IN ('recommended','normal','not_recommended','deferred','routine_practice')")
        op.create_check_constraint('ck_'+prefix+'_manual_focus_version', table, 'manual_focus_version >= 1')

def downgrade():
    for table in ('tasks', 'main_quests'):
        prefix = 'quests' if table == 'main_quests' else 'tasks'
        op.drop_constraint('ck_'+prefix+'_manual_focus_version', table)
        op.drop_constraint('ck_'+prefix+'_manual_focus', table)
        op.drop_column(table, 'manual_focus_version')
        op.drop_column(table, 'manual_focus_status')
