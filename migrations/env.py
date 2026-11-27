"""Alembic configuration; never store credentials in alembic.ini."""
from alembic import context
from alembic.util import CommandError
from sqlalchemy import create_engine, pool

from app.core.config import load_settings, postgres_url
from app.core.database import Base
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.quests import models as quest_models  # noqa: F401
from app.modules.tasks import models as task_models  # noqa: F401

from app.modules.activity import models as activity_models  # noqa: F401

from app.modules.growth import models as growth_models  # noqa: F401

from app.modules.ai_gateway import models as ai_models  # noqa: F401

from app.modules.startup_state import models as startup_models  # noqa: F401

from app.modules.task_recommendation import models as recommendation_models  # noqa: F401
from app.modules.startup_chat import breakdown_models  # noqa: F401
from app.modules.startup_chat import models as chat_models  # noqa: F401

from app.modules.startup_items import models as item_models  # noqa: F401

from app.modules.distractions import models as distraction_models  # noqa: F401

from app.modules.library import models as library_models  # noqa: F401
from app.modules.shining_memories.shared import models as memory_models  # noqa: F401
from app.modules.shining_memories.people import models as people_models  # noqa: F401
from app.modules.shining_memories.people import analysis_models as person_analysis_models  # noqa: F401
from app.modules.shining_memories.items import models as memory_items_models  # noqa: F401
from app.modules.shining_memories.wishes import models as memory_wishes_models  # noqa: F401

from app.modules.life_os import problem_models as life_os_problem_models  # noqa: F401
from app.modules.life_os import models as life_os_models  # noqa: F401
from app.modules.life_os import later_models as life_os_later_models  # noqa: F401
from app.modules.life_os import schedule_models  # noqa: F401

from app.modules.life_os import care  # noqa: F401

from app.modules.life_os import attractors  # noqa: F401

from app.modules.artifact_spirit import models as feature_visit_models  # noqa: F401

from app.modules.spirit_root import models as spirit_root_models  # noqa: F401

config = context.config


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(dialect_name="postgresql", target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    try:
        supplied = config.attributes.get("connection")
        if supplied is not None:
            migrate(supplied)
        else:
            settings = load_settings()
            if not settings.migration_database_url:
                raise CommandError("请先配置 MIGRATION_DATABASE_URL；本操作未连接数据库")
            url = postgres_url(settings.migration_database_url.get_secret_value())
            if url.port == 6543:
                raise CommandError("迁移请使用直连或 session pooler，不使用 6543 transaction pooler")
            engine = create_engine(url, poolclass=pool.NullPool, hide_parameters=True,
                                   connect_args={"connect_timeout": 5, "options": "-c statement_timeout=30000"})
            try:
                with engine.connect() as connection:
                    migrate(connection)
            finally:
                engine.dispose()
    except CommandError:
        raise
    except Exception:
        raise CommandError("迁移失败；请检查连接、权限和版本。连接详情已隐藏") from None
