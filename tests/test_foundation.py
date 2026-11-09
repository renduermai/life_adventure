import io
import logging
import re
import subprocess
import sys
from unittest.mock import MagicMock

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.core.config import ROOT, Settings, postgres_url
from app.core.database import Database, EXPECTED_REVISION
from app.core.logging import SafeFormatter


@pytest.mark.parametrize("path,title", [("/", "营地门牌"), ("/journey", "冒险地图"), ("/settings", "营地设置")])
def test_pages_and_navigation(client, path, title):
    result = client.get(path)
    assert result.status_code == 200
    assert f"<h1>{title}</h1>" in result.text
    assert 'aria-current="page"' in result.text
    for target in ("/", "/journey", "/settings"):
        assert f'href="{target}"' in result.text
    assert "阶段 1" in result.text or "连接状态" in result.text


@pytest.mark.parametrize("path", ["/static/css/app.css", "/static/js/app.js", "/static/js/theme.js"])
def test_assets_are_local(client, path):
    result = client.get(path)
    assert result.status_code == 200
    assert result.content


def test_readiness_is_not_liveness(client):
    assert client.get("/health/live").json()["status"] == "ok"
    ready = client.get("/health/ready")
    assert ready.status_code == 503
    assert ready.json()["status"] == "not_configured"


def test_security_headers_and_request_ids(client):
    first, second = client.get("/"), client.get("/")
    assert re.fullmatch("[0-9a-f]{32}", first.headers["x-request-id"])
    assert first.headers["x-request-id"] != second.headers["x-request-id"]
    assert "frame-ancestors 'none'" in first.headers["content-security-policy"]
    assert first.headers["x-content-type-options"] == "nosniff"


def test_unknown_route_and_write_rejected(client):
    assert client.get("/no-such-page").status_code == 404
    assert client.post("/settings", json={"database_url": "secret"}).status_code == 405


def test_unexpected_error_never_leaks(client, application):
    @application.get("/test-error")
    def error():
        raise RuntimeError("postgresql://user:private-password@host/db")
    response = client.get("/test-error")
    assert response.status_code == 500
    assert "private-password" not in response.text
    assert response.json()["request_id"] == response.headers["x-request-id"]


@pytest.mark.parametrize("value", ["sqlite:///db.sqlite", "invalid-secret", "postgresql://user:private-password@remote/db", "postgresql://localhost/"])
def test_invalid_database_config_is_redacted(value):
    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None, database_url=value)
    assert value not in str(caught.value)
    assert "private-password" not in str(caught.value)


def test_settings_file_env_precedence_and_secrets(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("APP_TIMEZONE=UTC\nDATABASE_URL=postgresql://user:private-password@localhost/db\n", encoding="utf-8")
    monkeypatch.setenv("APP_TIMEZONE", "Asia/Shanghai")
    settings = Settings(_env_file=env_file)
    assert settings.app_timezone == "Asia/Shanghai"
    assert "private-password" not in repr(settings)
    assert settings.database_url.get_secret_value().endswith("@localhost/db")


def test_empty_database_settings_and_timezone():
    assert Settings(_env_file=None, database_url="").database_url is None
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_timezone="Invalid/Timezone")


def test_postgres_url_normalization():
    url = postgres_url("postgres://user:encoded%40pass@remote.example/db?sslmode=require")
    assert url.drivername == "postgresql+psycopg"
    assert url.password == "encoded@pass"


def test_logger_redacts_dsn_and_tokens():
    record = logging.LogRecord("test", logging.ERROR, "", 0,
                               "postgresql://u:secret@host/db api_key=private-key", (), None)
    output = SafeFormatter().format(record)
    assert "secret" not in output and "private-key" not in output
    assert "REDACTED" in output


@pytest.mark.parametrize("exists,revisions,state", [(None, [], "migration_required"), ("alembic_version", [], "migration_required"), ("alembic_version", ["other"], "migration_required"), ("alembic_version", [EXPECTED_REVISION], "ready")])
def test_readiness_state_mapping(exists, revisions, state):
    # Unit simulation, NOT evidence of a real PostgreSQL connection.
    db = Database(Settings(_env_file=None))
    db.engine = MagicMock()
    conn = db.engine.connect.return_value.__enter__.return_value
    conn.execute.return_value.scalar.return_value = exists
    conn.execute.return_value.scalars.return_value.all.return_value = revisions
    assert db.status().state == state


def test_database_failure_is_generic():
    db = Database(Settings(_env_file=None))
    db.engine = MagicMock()
    db.engine.connect.side_effect = OperationalError("private SQL", {}, Exception("secret DSN"))
    assert db.status().state == "unavailable"
    assert "secret" not in db.status().message


def test_transaction_without_configuration_fails():
    db = Database(Settings(_env_file=None))
    with pytest.raises(RuntimeError, match="尚未配置"):
        with db.transaction():
            pass


def test_offline_migration_generates_postgres_sql():
    config = Config(str(ROOT / "alembic.ini"), output_buffer=io.StringIO())
    command.upgrade(config, "head", sql=True)
    sql = config.output_buffer.getvalue()
    assert "CREATE TABLE alembic_version" in sql
    assert EXPECTED_REVISION in sql
    assert "CREATE TABLE tasks" in sql
    assert "uq_task_completion_event" in sql
    assert "CREATE TABLE task_commands" in sql
    reverse = Config(str(ROOT / "alembic.ini"), output_buffer=io.StringIO())
    command.downgrade(reverse, f"{EXPECTED_REVISION}:base", sql=True)
    assert "DELETE FROM alembic_version" in reverse.output_buffer.getvalue()
    assert "DROP TABLE users" in reverse.output_buffer.getvalue()


def test_migration_with_invalid_credentials_fails_safely(tmp_path, monkeypatch):
    # Windows drops empty environment values in child processes; an invalid
    # explicit value reliably overrides any real local .env configuration.
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "invalid-test-connection")
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert result.returncode != 0
    assert "invalid-test-connection" not in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr
