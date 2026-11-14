import pytest
from app.modules.startup_state.router import locate, StateInput
from pydantic import ValidationError
from uuid import uuid4
@pytest.mark.parametrize('p,e,expected',[(0,0,'激活区'),(49,50,'投入区'),(50,50,'降噪区'),(100,0,'修复区'),(100,100,'降噪区')])
def test_quadrants(p,e,expected): assert locate(p,e)==expected
@pytest.mark.parametrize('value',[-1,101,1.2,True])
def test_invalid_pressure(value):
 with pytest.raises(ValidationError): StateInput(pressure=value,energy=50,confirmed=True,request_id=uuid4(),expected_generation=0)
