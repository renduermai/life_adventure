from decimal import Decimal
from uuid import uuid4
import pytest
from app.modules.shining_memories.wishes.service import change
from app.modules.shining_memories.wishes.schemas import Create

def test_price_changes():
    assert change(Decimal('5000'),Decimal('4200'),True)['percentage']=='16.00'
    assert change(Decimal('5000'),Decimal('5500'),True)['direction']=='up'
    assert change(Decimal('0'),Decimal('100'),True)['percentage'] is None
    assert change(Decimal('5000'),Decimal('5000'),False)['text']=='暂无价格变化记录'
@pytest.mark.parametrize('price',['-1','NaN','1.234','1000000000000'])
def test_invalid_price(price):
    with pytest.raises(ValueError):Create(request_id=uuid4(),name='心愿',price=price)
