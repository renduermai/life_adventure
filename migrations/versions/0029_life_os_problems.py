"""Problem types, distinct events, evidence and versioned edits."""
from alembic import op
import sqlalchemy as sa
revision='0029_life_os_problems'
down_revision='0028_life_os_core'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("life_os_analyses",sa.Column("note_scope",sa.JSON(),nullable=True))
    op.create_table('life_os_problems',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('name_key', sa.String(length=200), nullable=False),
    sa.Column('mechanism', sa.String(length=1000), nullable=False),
    sa.Column('notes', sa.String(length=2000), nullable=False),
    sa.Column('manual_fields', sa.JSON(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('merged_into', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'user_id', name='uq_life_problem_owner'),
    sa.UniqueConstraint('user_id', 'name_key', name='uq_life_problem_name')
    )
    op.create_index(op.f('ix_life_os_problems_user_id'), 'life_os_problems', ['user_id'], unique=False)
    op.create_table('life_os_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=160), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('confirmed','pending')", name='ck_life_event_status'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'user_id', name='uq_life_event_owner')
    )
    op.create_index(op.f('ix_life_os_events_user_id'), 'life_os_events', ['user_id'], unique=False)
    op.create_table('life_os_event_sources',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('event_id', sa.Uuid(), nullable=False),
    sa.Column('message_id', sa.Uuid(), nullable=True),
    sa.Column('note_id', sa.Uuid(), nullable=True),
    sa.CheckConstraint('(message_id IS NULL) <> (note_id IS NULL)', name='ck_life_source_one'),
    sa.ForeignKeyConstraint(['event_id', 'user_id'], ['life_os_events.id', 'life_os_events.user_id'], ),
    sa.ForeignKeyConstraint(['message_id', 'user_id'], ['life_os_messages.id', 'life_os_messages.user_id'], ),
    sa.ForeignKeyConstraint(['note_id', 'user_id'], ['distraction_notes.id', 'distraction_notes.user_id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'message_id', name='uq_life_event_message'),
    sa.UniqueConstraint('user_id', 'note_id', name='uq_life_event_note')
    )
    op.create_index(op.f('ix_life_os_event_sources_user_id'), 'life_os_event_sources', ['user_id'], unique=False)
    op.create_table('life_os_event_problems',
    sa.Column('event_id', sa.Uuid(), nullable=False),
    sa.Column('problem_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['event_id', 'user_id'], ['life_os_events.id', 'life_os_events.user_id'], ),
    sa.ForeignKeyConstraint(['problem_id', 'user_id'], ['life_os_problems.id', 'life_os_problems.user_id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('event_id', 'problem_id')
    )
    op.create_table('life_os_experiences',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('event_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('text', sa.String(length=1000), nullable=False),
    sa.Column('outcome', sa.String(length=20), nullable=False),
    sa.Column('source_message_id', sa.Uuid(), nullable=True),
    sa.Column('source_quote', sa.String(length=400), nullable=True),
    sa.Column('dedup_key', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('suggestion','observation','action','feedback')", name='ck_life_experience_kind'),
    sa.CheckConstraint("outcome IN ('unknown','helpful','unhelpful','mixed')", name='ck_life_experience_outcome'),
    sa.ForeignKeyConstraint(['event_id', 'user_id'], ['life_os_events.id', 'life_os_events.user_id'], ),
    sa.ForeignKeyConstraint(['source_message_id'], ['life_os_messages.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'dedup_key', name='uq_life_experience_dedup')
    )
    op.create_index(op.f('ix_life_os_experiences_user_id'), 'life_os_experiences', ['user_id'], unique=False)
    op.create_table('life_os_problem_history',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('target_id', sa.Uuid(), nullable=False),
    sa.Column('action', sa.String(length=40), nullable=False),
    sa.Column('request_id', sa.Uuid(), nullable=False),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('before', sa.JSON(), nullable=False),
    sa.Column('after', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'request_id', name='uq_life_history_request')
    )
    op.create_index(op.f('ix_life_os_problem_history_user_id'), 'life_os_problem_history', ['user_id'], unique=False)
    op.add_column('life_os_analyses', sa.Column('experience_status', sa.String(length=20), nullable=True))
    op.add_column('life_os_analyses', sa.Column('experience_error', sa.String(length=40), nullable=True))

def downgrade():
    op.drop_column("life_os_analyses","note_scope")
    op.drop_column("life_os_analyses","experience_error")
    op.drop_column("life_os_analyses","experience_status")
    op.drop_table('life_os_problem_history')
    op.drop_table('life_os_experiences')
    op.drop_table('life_os_event_problems')
    op.drop_table('life_os_event_sources')
    op.drop_table('life_os_events')
    op.drop_table('life_os_problems')
