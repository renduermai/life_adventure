"""PostgreSQL lifecycle and truthful readiness checks; no auto-created tables."""
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import Settings, postgres_url

EXPECTED_REVISION = "0016_startup_items"
logger = logging.getLogger("adventure_camp")


class Base(DeclarativeBase):
    pass


@dataclass(frozen=True)
class DatabaseStatus:
    state: str
    message: str

    @property
    def ready(self) -> bool:
        return self.state == "ready"


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine = None
        self.sessions = None
        if settings.database_url:
            self.engine = create_engine(
                postgres_url(settings.database_url.get_secret_value()),
                pool_pre_ping=True, pool_size=2, max_overflow=2, pool_timeout=5,
                connect_args={"connect_timeout": 5, "options": "-c statement_timeout=5000"},
                hide_parameters=True,
            )
            self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        """One transaction owner per use case; services must not commit separately."""
        if self.sessions is None:
            raise RuntimeError("数据库尚未配置")
        with self.sessions.begin() as session:
            yield session

    def status(self) -> DatabaseStatus:
        if self.engine is None:
            return DatabaseStatus("not_configured", "数据库尚未配置")
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                exists = connection.execute(text("SELECT to_regclass('public.alembic_version')")).scalar()
                if not exists:
                    return DatabaseStatus("migration_required", "数据库已连接，尚未执行基础迁移")
                revisions = connection.execute(text("SELECT version_num FROM public.alembic_version")).scalars().all()
                if revisions != [EXPECTED_REVISION]:
                    return DatabaseStatus("migration_required", "数据库已连接，迁移版本与应用不一致")
            return DatabaseStatus("ready", "数据库连接与迁移版本正常")
        except Exception as error:
            logger.warning("database_check_failed type=%s", type(error).__name__)
            return DatabaseStatus("unavailable", "数据库暂不可用，请检查本地配置与网络")

    def dispose(self) -> None:
        if self.engine is not None:
            self.engine.dispose()
