"""Independent paired schedule suggestions; original templates untouched."""
from alembic import op
import sqlalchemy as sa
revision='0031_life_os_schedules'
down_revision='0030_life_os_layers_modes_scenes'
branch_labels=None
depends_on=None
def upgrade():
    op.create_table('life_os_schedule_runs',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('user_id',sa.Uuid(),sa.ForeignKey('users.id'),nullable=False),sa.Column('fingerprint',sa.String(64),nullable=False),sa.Column('status',sa.String(20),nullable=False),sa.Column('error_code',sa.String(50)),sa.Column('context',sa.JSON(),nullable=False),sa.Column('result',sa.JSON()),sa.Column('usage',sa.JSON()),sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index('ix_life_os_schedule_runs_user_id','life_os_schedule_runs',['user_id'])
    op.create_index('ix_life_os_schedule_runs_fingerprint','life_os_schedule_runs',['fingerprint'])
def downgrade():
    op.drop_table('life_os_schedule_runs')
