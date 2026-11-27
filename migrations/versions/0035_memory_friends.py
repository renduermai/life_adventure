"""Add friend records and their latest relationship mapping."""

from alembic import op
import sqlalchemy as sa

revision = '0035_memory_friends'
down_revision = '0034_life_os_note_input'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('memory_people', sa.Column('kind', sa.String(8), server_default='mentor', nullable=False))
    op.add_column('memory_people', sa.Column('base_location', sa.String(120)))
    op.add_column('memory_people', sa.Column('friend_mapping', sa.JSON()))
    op.create_check_constraint(
        'ck_memory_person_kind_location', 'memory_people',
        "(kind = 'mentor' AND base_location IS NULL) OR "
        "(kind = 'friend' AND base_location IS NOT NULL AND length(trim(base_location)) > 0)",
    )


def downgrade():
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM memory_people WHERE kind = 'friend') THEN
                RAISE EXCEPTION 'Cannot downgrade while friend records exist';
            END IF;
        END $$;
    """)
    op.drop_constraint('ck_memory_person_kind_location', 'memory_people', type_='check')
    op.drop_column('memory_people', 'friend_mapping')
    op.drop_column('memory_people', 'base_location')
    op.drop_column('memory_people', 'kind')
