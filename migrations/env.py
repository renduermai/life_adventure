"""Alembic configuration; never store credentials in alembic.ini."""
from alembic import context
from alembic.util import CommandError
from sqlalchemy import create_engine, pool

from app.core.config import load_settings, postgres_url
from app.core.database import Base

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
