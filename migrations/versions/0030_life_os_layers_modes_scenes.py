"""Life OS double layers, operating modes, and original scene schedules."""
from alembic import op
import sqlalchemy as sa

revision='0030_life_os_layers_modes_scenes'
down_revision='0029_life_os_problems'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('life_os_layer_experiences',
        sa.Column('id',sa.Uuid(),nullable=False),sa.Column('user_id',sa.Uuid(),nullable=False),
        sa.Column('model',sa.String(20),nullable=False),sa.Column('layer',sa.String(40),nullable=False),
        sa.Column('occurred_on',sa.Date(),nullable=False),sa.Column('event',sa.String(1200),nullable=False),
        sa.Column('experience',sa.String(1600),nullable=False),sa.Column('recommendation',sa.String(1200),nullable=False),
        sa.Column('notes',sa.String(1200),nullable=False),sa.Column('source',sa.String(12),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('deleted_at',sa.DateTime(timezone=True)),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.ForeignKeyConstraint(['user_id'],['users.id'],ondelete='CASCADE'),sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id','user_id',name='uq_life_layer_experience_owner'),
        sa.CheckConstraint("model IN ('life','need')",name='ck_life_layer_model'),
        sa.CheckConstraint("source IN ('user','ai')",name='ck_life_layer_source'))
    op.create_index('ix_life_os_layer_experiences_user_id','life_os_layer_experiences',['user_id'])
    op.create_table('life_os_layer_experience_revisions',
        sa.Column('id',sa.Uuid(),nullable=False),sa.Column('experience_id',sa.Uuid(),nullable=False),
        sa.Column('user_id',sa.Uuid(),nullable=False),sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('action',sa.String(12),nullable=False),sa.Column('snapshot',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.ForeignKeyConstraint(['experience_id','user_id'],['life_os_layer_experiences.id','life_os_layer_experiences.user_id'],ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'],['users.id'],ondelete='CASCADE'),sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_life_os_layer_experience_revisions_experience_id','life_os_layer_experience_revisions',['experience_id'])
    op.create_index('ix_life_os_layer_experience_revisions_user_id','life_os_layer_experience_revisions',['user_id'])
    op.create_table('life_os_operating_modes',
        sa.Column('user_id',sa.Uuid(),nullable=False),sa.Column('follows_ai',sa.Boolean(),nullable=False),
        sa.Column('actual_mode',sa.String(12)),sa.Column('suggested_mode',sa.String(12)),
        sa.Column('reason',sa.String(240),nullable=False),sa.Column('analysis_id',sa.Uuid()),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.ForeignKeyConstraint(['user_id'],['users.id'],ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['analysis_id'],['life_os_analyses.id'],ondelete='SET NULL'),sa.PrimaryKeyConstraint('user_id'),
        sa.CheckConstraint("actual_mode IS NULL OR actual_mode IN ('green','yellow','red','blue')",name='ck_life_actual_mode'),
        sa.CheckConstraint("suggested_mode IS NULL OR suggested_mode IN ('green','yellow','red','blue')",name='ck_life_suggested_mode'))
    op.create_table('life_os_operating_mode_history',
        sa.Column('id',sa.Uuid(),nullable=False),sa.Column('user_id',sa.Uuid(),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('action',sa.String(20),nullable=False),
        sa.Column('actual_mode',sa.String(12)),sa.Column('suggested_mode',sa.String(12)),
        sa.Column('follows_ai',sa.Boolean(),nullable=False),sa.Column('reason',sa.String(240),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.ForeignKeyConstraint(['user_id'],['users.id'],ondelete='CASCADE'),sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_life_os_operating_mode_history_user_id','life_os_operating_mode_history',['user_id'])
    op.create_table('life_os_scenes',
        sa.Column('id',sa.Uuid(),nullable=False),sa.Column('user_id',sa.Uuid(),nullable=False),sa.Column('name',sa.String(80),nullable=False),
        sa.Column('daily_slots',sa.JSON(),nullable=False),sa.Column('weekly_rhythm',sa.JSON(),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('deleted_at',sa.DateTime(timezone=True)),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.ForeignKeyConstraint(['user_id'],['users.id'],ondelete='CASCADE'),sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id','user_id',name='uq_life_scene_owner'))
    op.create_index('ix_life_os_scenes_user_id','life_os_scenes',['user_id'])
    op.create_table('life_os_active_scene',
        sa.Column('user_id',sa.Uuid(),nullable=False),sa.Column('scene_id',sa.Uuid(),nullable=False),
        sa.ForeignKeyConstraint(['user_id'],['users.id'],ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['scene_id','user_id'],['life_os_scenes.id','life_os_scenes.user_id']),
        sa.PrimaryKeyConstraint('user_id'),sa.UniqueConstraint('scene_id','user_id',name='uq_life_active_scene_owner'))
    op.create_table('life_os_scene_revisions',
        sa.Column('id',sa.Uuid(),nullable=False),sa.Column('scene_id',sa.Uuid(),nullable=False),sa.Column('user_id',sa.Uuid(),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('action',sa.String(12),nullable=False),sa.Column('snapshot',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.ForeignKeyConstraint(['scene_id','user_id'],['life_os_scenes.id','life_os_scenes.user_id'],ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'],['users.id'],ondelete='CASCADE'),sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_life_os_scene_revisions_scene_id','life_os_scene_revisions',['scene_id'])
    op.create_index('ix_life_os_scene_revisions_user_id','life_os_scene_revisions',['user_id'])

def downgrade():
    op.drop_table('life_os_scene_revisions');op.drop_table('life_os_active_scene');op.drop_index('ix_life_os_scenes_user_id',table_name='life_os_scenes');op.drop_table('life_os_scenes')
    op.drop_index('ix_life_os_operating_mode_history_user_id',table_name='life_os_operating_mode_history');op.drop_table('life_os_operating_mode_history');op.drop_table('life_os_operating_modes')
    op.drop_index('ix_life_os_layer_experience_revisions_user_id',table_name='life_os_layer_experience_revisions');op.drop_index('ix_life_os_layer_experience_revisions_experience_id',table_name='life_os_layer_experience_revisions');op.drop_table('life_os_layer_experience_revisions')
    op.drop_index('ix_life_os_layer_experiences_user_id',table_name='life_os_layer_experiences');op.drop_table('life_os_layer_experiences')
