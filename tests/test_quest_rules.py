from types import SimpleNamespace
from uuid import uuid4

import pytest
from starlette.requests import Request
from fastapi import HTTPException

from app.modules.identity.service import token_hash, update_profile
from app.modules.quests.router import same_origin
from app.modules.quests.service import date_value, progress, set_milestone_fields, set_quest_fields, validate_title


@pytest.mark.parametrize("title", ["", "  ", "x" * 161])
def test_invalid_title(title):
    with pytest.raises(ValueError):
        validate_title(title)


def test_dates_and_progress():
    quest = SimpleNamespace()
    with pytest.raises(ValueError):
        set_quest_fields(quest, "目标", "", "2026-12-01", "2026-01-01")
    with pytest.raises(ValueError):
        date_value("invalid")
    assert progress([]) is None
    assert progress([SimpleNamespace(status="pending"), SimpleNamespace(status="completed")]) == 50


def test_milestone_validation():
    with pytest.raises(ValueError):
        set_milestone_fields(SimpleNamespace(), "", "", "")


def test_profile_and_tokens():
    user = SimpleNamespace()
    update_profile(user, " 新昵称 ", "Asia/Shanghai")
    assert user.display_name == "新昵称"
    with pytest.raises(ValueError):
        update_profile(user, "昵称", "No/Such_Timezone")
    assert token_hash("one") != token_hash("two")
    assert "one" not in token_hash("one")


@pytest.mark.parametrize("origin,allowed", [("http://testserver", True), ("https://attacker.example", False), (None, False)])
def test_post_origin(origin, allowed):
    headers = [(b"host", b"testserver")]
    if origin:
        headers.append((b"origin", origin.encode()))
    request = Request({"type": "http", "method": "POST", "scheme": "http", "path": "/", "headers": headers, "server": ("testserver", 80)})
    if allowed:
        same_origin(request)
    else:
        with pytest.raises(HTTPException) as error:
            same_origin(request)
        assert error.value.status_code == 403
