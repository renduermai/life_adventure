from alembic import op
import sqlalchemy as sa
revision='0033_life_os_attractors'
down_revision='0032_life_os_care'
branch_labels=None
depends_on=None
def upgrade():
    op.create_table('life_os_attractor_runs',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('user_id',sa.Uuid(),sa.ForeignKey('users.id'),nullable=False),sa.Column('scope',sa.String(64),nullable=False),sa.Column('fingerprint',sa.String(64),nullable=False),sa.Column('status',sa.String(20),nullable=False),sa.Column('error_code',sa.String(50)),sa.Column('snapshot',sa.JSON(),nullable=False),sa.Column('result',sa.JSON()),sa.Column('usage',sa.JSON()),sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index('ix_life_os_attractor_runs_user_id','life_os_attractor_runs',['user_id'])
    op.create_index('ix_life_os_attractor_runs_scope','life_os_attractor_runs',['scope'])
def downgrade():op.drop_table('life_os_attractor_runs')
