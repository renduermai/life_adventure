from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.modules.life_os.problem_schemas import EventProposal,Feedback

def proposal(**changes):
    return dict(relation='uncertain',existing_event_id=None,title='测试事件',evidence_quote='真实原文',action_quote='',feedback_quote='',outcome='unknown',problems=[])|changes

def test_uncertainty_and_continuation_contracts():
    assert EventProposal(**proposal()).relation=='uncertain'
    for values in [proposal(existing_event_id=uuid4()),proposal(relation='new',existing_event_id=uuid4()),proposal(relation='continue'),proposal(outcome='helpful')]:
        with pytest.raises(ValidationError):EventProposal(**values)

def test_feedback_requires_a_reported_result_for_effectiveness():
    with pytest.raises(ValidationError):Feedback(request_id=uuid4(),action='以后想整理',feedback='',outcome='helpful')
