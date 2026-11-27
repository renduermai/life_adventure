from datetime import date,timedelta
from decimal import Decimal
import pytest
from app.modules.shining_memories.items.service import cost
from app.modules.shining_memories.items.schemas import Create
from uuid import uuid4

def test_cost_today_and_long_term():
    d=date(2026,11,22)
    assert cost(Decimal('8000'),d,d)==(1,Decimal('8000'))
    assert cost(Decimal('8000'),d-timedelta(days=400),d)==(400,Decimal('20'))
    assert cost(Decimal('0'),d,d)==(1,Decimal('0'))

@pytest.mark.parametrize('value',['-1','1.234','NaN','1000000000000'])
def test_invalid_price(value):
    with pytest.raises(ValueError):Create(request_id=uuid4(),name='测试',purchase_date='2026-01-01',purchase_price=value)
