import pytest
from pydantic import ValidationError
from app.modules.life_os.schemas import Estimate, Send
from uuid import uuid4

@pytest.mark.parametrize('value',[True,'40',-1,101])
def test_estimates_reject_false_precision_and_out_of_range(value):
    with pytest.raises(ValidationError):Estimate(value=value,reason='测试')

def test_unknown_estimate_and_raw_whitespace():
    assert Estimate(value=None,reason='信息不足').value is None
    text='  原始记录\n保留空白  '
    assert Send(request_id=uuid4(),content=text).content==text
    with pytest.raises(ValidationError):Send(request_id=uuid4(),content='  ')
