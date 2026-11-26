from alembic import op
import sqlalchemy as sa
revision='0032_life_os_care'
down_revision='0031_life_os_schedules'
branch_labels=None
depends_on=None
def upgrade():
    op.create_table('life_os_care',sa.Column('user_id',sa.Uuid(),sa.ForeignKey('users.id'),primary_key=True),sa.Column('data',sa.JSON(),nullable=False),sa.Column('version',sa.Integer(),nullable=False))
    op.create_table('life_os_care_days',sa.Column('user_id',sa.Uuid(),sa.ForeignKey('users.id'),primary_key=True),sa.Column('day',sa.Date(),primary_key=True),sa.Column('data',sa.JSON(),nullable=False))
def downgrade():
    op.drop_table('life_os_care_days');op.drop_table('life_os_care')
