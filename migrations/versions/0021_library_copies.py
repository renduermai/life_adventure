"""Idempotent successful-copy receipts."""
from alembic import op
import sqlalchemy as sa
revision='0021_library_copies'
down_revision='0020_library_links'
branch_labels=None
depends_on=None


def upgrade():
    op.create_unique_constraint('uq_library_id_user','library_links',['id','user_id'])
    op.create_table('library_copy_receipts',
        sa.Column('user_id',sa.Uuid(),sa.ForeignKey('users.id'),primary_key=True),
        sa.Column('request_id',sa.Uuid(),primary_key=True),
        sa.Column('link_id',sa.Uuid(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['link_id','user_id'],['library_links.id','library_links.user_id']))


def downgrade():
    op.drop_table('library_copy_receipts')
    op.drop_constraint('uq_library_id_user','library_links',type_='unique')
