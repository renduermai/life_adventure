"""Owner-scoped task bookmarks; usage will count successful copies."""
from alembic import op
import sqlalchemy as sa
revision='0020_library_links'
down_revision='0019_distraction_classification'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('library_links',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('user_id',sa.Uuid(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('description',sa.String(500),nullable=False),
        sa.Column('url',sa.Text(),nullable=False),
        sa.Column('main_quest_id',sa.Uuid()),sa.Column('task_id',sa.Uuid()),
        sa.Column('click_count',sa.BigInteger(),nullable=False,server_default=sa.text('0')),
        sa.Column('version',sa.Integer(),nullable=False,server_default=sa.text('1')),
        sa.Column('create_request_id',sa.Uuid(),nullable=False),
        sa.Column('create_fingerprint',sa.String(64),nullable=False),
        sa.Column('deleted_at',sa.DateTime(timezone=True)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['main_quest_id','user_id'],['main_quests.id','main_quests.user_id']),
        sa.ForeignKeyConstraint(['task_id','user_id'],['tasks.id','tasks.user_id']),
        sa.CheckConstraint('(main_quest_id IS NULL) <> (task_id IS NULL)',name='ck_library_one_target'),
        sa.CheckConstraint('click_count >= 0 AND version >= 1',name='ck_library_counters'),
        sa.CheckConstraint('char_length(description) BETWEEN 1 AND 500',name='ck_library_description'),
        sa.CheckConstraint('char_length(url) BETWEEN 1 AND 2048',name='ck_library_url_length'),
        sa.UniqueConstraint('user_id','create_request_id',name='uq_library_create_request'))
    op.create_index('ix_library_owner_sort','library_links',['user_id','click_count','created_at','id'])
    op.create_index('ix_library_quest','library_links',['main_quest_id','user_id'])
    op.create_index('ix_library_task','library_links',['task_id','user_id'])


def downgrade():
    op.drop_table('library_links')
