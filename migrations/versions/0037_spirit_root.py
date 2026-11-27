"""Store spirit root originals, entries and related evidence."""

from alembic import op
import sqlalchemy as sa

revision = '0037_spirit_root'
down_revision = '0036_feature_visits'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'spirit_root_sources',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('digest', sa.String(64), nullable=False),
        sa.Column('original', sa.Text(), nullable=False),
        sa.Column('state', sa.String(10), nullable=False),
        sa.Column('attempt_id', sa.Uuid(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('error_code', sa.String(60)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'digest', name='uq_spirit_root_source_digest'),
        sa.UniqueConstraint('id', 'user_id', name='uq_spirit_root_source_owner'),
        sa.CheckConstraint("state IN ('running','succeeded','failed')", name='ck_spirit_root_source_state'),
    )
    op.create_table(
        'spirit_root_entries',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(8), nullable=False),
        sa.Column('label', sa.String(80), nullable=False),
        sa.Column('label_key', sa.String(256), nullable=False),
        sa.UniqueConstraint('user_id', 'kind', 'label_key', name='uq_spirit_root_entry_label'),
        sa.UniqueConstraint('id', 'user_id', name='uq_spirit_root_entry_owner'),
        sa.CheckConstraint("kind IN ('talent','signal')", name='ck_spirit_root_entry_kind'),
    )
    op.create_table(
        'spirit_root_observations',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('source_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid()),
        sa.Column('suggested_id', sa.Uuid()),
        sa.Column('kind', sa.String(8), nullable=False),
        sa.Column('label', sa.String(80), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('strength', sa.String(12)),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('quote', sa.Text(), nullable=False),
        sa.Column('linked_talents', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['source_id', 'user_id'], ['spirit_root_sources.id', 'spirit_root_sources.user_id'],
                                name='fk_spirit_root_observation_source'),
        sa.ForeignKeyConstraint(['entry_id', 'user_id'], ['spirit_root_entries.id', 'spirit_root_entries.user_id'],
                                name='fk_spirit_root_observation_entry'),
        sa.ForeignKeyConstraint(['suggested_id', 'user_id'], ['spirit_root_entries.id', 'spirit_root_entries.user_id'],
                                name='fk_spirit_root_observation_suggestion'),
        sa.UniqueConstraint('source_id', 'entry_id', name='uq_spirit_root_entry_source'),
    )
    op.create_index('ix_spirit_root_observations_entry_id', 'spirit_root_observations', ['entry_id'])
    op.create_index('ix_spirit_root_observations_user_id', 'spirit_root_observations', ['user_id'])


def downgrade():
    op.drop_table('spirit_root_observations')
    op.drop_table('spirit_root_entries')
    op.drop_table('spirit_root_sources')
