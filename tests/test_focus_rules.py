from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from app.modules.activity.service import duration

def test_server_clock_countdown_and_pause():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session = SimpleNamespace(accumulated_seconds=10, status='running', resumed_at=now-timedelta(seconds=70), mode='countdown', target_seconds=60)
    assert duration(session, now) == 60
    session.status = 'paused'
    assert duration(session, now) == 10
    session.status = 'running'
    session.mode = 'elapsed'
    session.resumed_at = now + timedelta(seconds=10)
    assert duration(session, now) == 10
