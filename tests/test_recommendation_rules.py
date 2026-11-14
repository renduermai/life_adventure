import pytest
from types import SimpleNamespace
from pydantic import ValidationError
from app.modules.task_recommendation.service import evaluate,Features,fingerprint
@pytest.mark.parametrize('energy,pressure,expected',[(100,0,'green'),(0,100,'red')])
def test_state_matching(energy,pressure,expected):
 feature={'effort':3,'barrier':3,'clear_next':True,'reason':'test'}
 assert evaluate(feature,SimpleNamespace(energy=energy,pressure=pressure))[0]==expected

def test_unknown_not_white():assert evaluate({},None)[0] is None

def test_fake_task_id_rejected():
 with pytest.raises(ValidationError):Features(keyword='test',quadrants=['投入区'],effort=1,barrier=1,clear_next=True,reason='test',task_id='invented')

def test_fingerprint_changes():assert fingerprint({'title':'a'})!=fingerprint({'title':'b'})
