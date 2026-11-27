"""Independent original thoughts, without AI or task relations."""
from alembic import op
import sqlalchemy as sa

revision = '0018_distraction_notes'
down_revision = '0017_item_analysis'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('distraction_notes',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
        sa.Column('create_request_id', sa.Uuid(), nullable=False),
        sa.Column('create_fingerprint', sa.String(64), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('user_id', 'create_request_id', name='uq_distraction_note_request'),
        sa.UniqueConstraint('id', 'user_id', name='uq_distraction_note_owner'),
        sa.CheckConstraint('version >= 1', name='ck_distraction_note_version'),
        sa.CheckConstraint('char_length(content) BETWEEN 1 AND 5000', name='ck_distraction_note_length'))
    op.create_index('ix_distraction_notes_user_created', 'distraction_notes', ['user_id', 'created_at', 'id'])


def downgrade():
    op.drop_table('distraction_notes')
