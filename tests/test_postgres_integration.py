"""Opt-in real PostgreSQL tests; a unique schema is always cleaned up."""
import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.core.config import ROOT, postgres_url
from app.core.database import EXPECTED_REVISION


@pytest.mark.integration
def test_real_postgres_migration_persistence_and_rollback():
    raw_url = os.environ.get("TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("TEST_DATABASE_URL 未配置；真实 PostgreSQL 迁移与持久化尚未验收")
    engine = create_engine(postgres_url(raw_url), hide_parameters=True, connect_args={"connect_timeout": 5})
    schema = "ac_test_" + uuid4().hex
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            config = Config(str(ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            command.upgrade(config, "head")
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == EXPECTED_REVISION
            connection.execute(text("CREATE TABLE persistence_probe (id integer primary key)"))
            connection.execute(text("INSERT INTO persistence_probe VALUES (1)"))
        # A different connection observes a committed record.
        with engine.connect() as connection:
            assert connection.execute(text(f'SELECT count(*) FROM "{schema}".persistence_probe')).scalar_one() == 1
        with pytest.raises(RuntimeError):
            with engine.begin() as connection:
                connection.execute(text(f'INSERT INTO "{schema}".persistence_probe VALUES (2)'))
                raise RuntimeError("rollback probe")
        with engine.begin() as connection:
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            assert connection.execute(text("SELECT count(*) FROM persistence_probe")).scalar_one() == 1
            config.attributes["connection"] = connection
            command.downgrade(config, "base")
            assert connection.execute(text("SELECT count(*) FROM alembic_version")).scalar_one() == 0
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
