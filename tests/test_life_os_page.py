from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_life_os_page_and_assets_are_available():
    app = create_app(Settings(_env_file=None, database_url=None, migration_database_url=None))
    with TestClient(app) as client:
        response = client.get("/life-os")
        assert response.status_code == 200
        assert 'aria-current="page"' in response.text
        assert 'href="/life-os"' in response.text
        assert 'data-timezone="Asia/Shanghai"' in response.text
        assert 'id="life-os-date"' in response.text
        assert 'id="life-os-time"' in response.text
        assert client.get("/static/css/life_os.css").status_code == 200
        assert client.get("/static/js/life_os.js").status_code == 200


def test_life_os_has_chat_and_seven_future_sections():
    app = create_app(Settings(_env_file=None, database_url=None, migration_database_url=None))
    with TestClient(app) as client:
        html = client.get("/life-os").text
    for marker in (
        "life-os-entry-title", "life-os-problems-title", "life-os-layers-title",
        "life-os-modes-title", "life-os-daily-title", "life-os-weekly-title",
        "life-os-basics-title", "life-os-attractors-title",
    ):
        assert f'id="{marker}"' in html
    assert "保存并分析" in html
    assert 'id="life-os-form"' in html
    assert 'id="life-problem-list"' in html
    assert 'id="life-attractors"' in html
    assert "life_os_attractors.js" in html
