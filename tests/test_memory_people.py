from datetime import date,timedelta
import pytest
from app.modules.shining_memories.people.service import heat
from app.modules.shining_memories.people.schemas import PersonCreate,EventCreate


def test_heat_boundaries_and_unknown():
    today=date(2026,11,22)
    assert heat(None,today) is None
    assert heat(today,today)==100
    assert heat(today-timedelta(days=1095),today)==0
    assert heat(today-timedelta(days=2000),today)==0
    assert heat(today-timedelta(days=547),today)==50


def test_person_and_event_validation():
    from uuid import uuid4
    with pytest.raises(ValueError):PersonCreate(request_id=uuid4(),name=' ',relationship='老师')
    with pytest.raises(ValueError):EventCreate(request_id=uuid4(),event_date='2026-11-22',content='回忆',is_actual_contact='false')
