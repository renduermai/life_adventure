import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in ("DATABASE_URL", "MIGRATION_DATABASE_URL", "APP_TIMEZONE", "LOG_LEVEL", "APP_NAME"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def application():
    return create_app(Settings(_env_file=None, database_url=None, migration_database_url=None))


@pytest.fixture
def client(application):
    with TestClient(application) as test_client:
        yield test_client
