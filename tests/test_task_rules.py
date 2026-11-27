from datetime import date

import pytest

from app.modules.tasks.service import TaskError, fields, identifier, next_due


@pytest.mark.parametrize("anchor,rule,expected", [
    (date(2026, 12, 31), "daily", date(2027, 1, 1)),
    (date(2026, 12, 31), "weekly", date(2027, 1, 7)),
    (date(2028, 1, 31), "monthly", date(2028, 2, 29)),
    (date(2026, 1, 31), "monthly", date(2026, 2, 28)),
    (date(2026, 12, 15), "monthly", date(2027, 1, 15)),
])
def test_recurrence_dates(anchor, rule, expected):
    assert next_due(anchor, rule) == expected


@pytest.mark.parametrize("data", [
    {"title": " "}, {"title": "x" * 161}, {"title": "task", "due_date": "bad"},
    {"title": "task", "category": "x" * 61}, {"title": "task", "description": "x" * 5001},
    {"title": "task", "repeat_rule": "hourly"}, {"title": "task", "priority": "urgent"},
    {"title": "task", "milestone_id": "bad"},
])
def test_invalid_task_fields(data):
    with pytest.raises(ValueError):
        fields(data)


def test_recurrence_overflow_is_user_error():
    with pytest.raises(TaskError):
        next_due(date(9999, 12, 31), "daily")
    with pytest.raises(TaskError):
        next_due(date(9999, 12, 31), "monthly")
    assert identifier("") is None


def test_task_write_requires_origin(client):
    assert client.post("/tasks/create").status_code == 403
    assert client.post("/tasks/batch", headers={"origin": "https://elsewhere.example"}).status_code == 403
