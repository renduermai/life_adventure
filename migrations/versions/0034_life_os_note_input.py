from alembic import op
import sqlalchemy as sa
revision='0034_life_os_note_input'
down_revision='0033_life_os_attractors'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('life_os_messages',sa.Column('input_note_ids',sa.JSON(),nullable=True))
    op.alter_column('life_os_messages','content',existing_type=sa.String(4000),type_=sa.Text(),existing_nullable=False)
def downgrade():
    op.drop_column('life_os_messages','input_note_ids')
    # PostgreSQL rejects long rows rather than silently truncating originals.
    op.alter_column('life_os_messages','content',existing_type=sa.Text(),type_=sa.String(4000),existing_nullable=False)
