from datetime import date, timedelta
import pytest
from app.modules.activity.journal import period,local_datetime

def test_local_period_boundaries_and_dst():
    start,end,first,last=period('week','2026-11-10','Asia/Shanghai')
    assert first==date(2026,11,9) and last==date(2026,11,16)
    assert end-start==timedelta(days=7)
    start,end,_,_=period('day','2026-03-08','America/New_York')
    assert end-start==timedelta(hours=23)
    with pytest.raises(ValueError): local_datetime('2026-03-08T02:30','America/New_York')
    with pytest.raises(ValueError): period('year','2026-01-01','Asia/Shanghai')
