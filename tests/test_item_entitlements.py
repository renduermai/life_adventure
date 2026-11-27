from datetime import date,timedelta
from uuid import uuid4
import pytest
from app.modules.shining_memories.items.schemas import Create

@pytest.mark.parametrize('flag,expiry,valid',[(False,None,True),(True,None,False),(False,'2026-01-02',False),(True,'2025-12-31',False),(True,'2026-01-01',True),(True,'2026-01-02',True)])
def test_expiry_fields(flag,expiry,valid):
    values=dict(request_id=uuid4(),name='合成权益',purchase_date='2026-01-01',purchase_price='100',is_entitlement=flag,expires_at=expiry)
    if valid:assert Create(**values).is_entitlement==flag
    else:
        with pytest.raises(ValueError):Create(**values)
