from types import SimpleNamespace
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.modules.startup_chat.schemas import MessageInput, StateAdvice
from app.modules.startup_chat.service import context_messages


def advice(**values):
    return dict(reply='建议压力 70、能量 60，可以修改后确认。', ready=True, pressure=70,
                energy=60, difficulty='事太多', barrier='不知从哪开始', goal='先开始一件事') | values


@pytest.mark.parametrize('values', [dict(pressure=-1), dict(energy=101), dict(pressure=True), dict(energy=None), dict(ready='true'), dict(extra='unexpected')])
def test_advice_rejects_invalid_or_incomplete_ready_values(values):
    with pytest.raises(ValidationError):
        StateAdvice(**advice(**values))


def test_followup_allows_unknown_values_and_bounded_history():
    value = StateAdvice(**advice(ready=False, pressure=None, energy=None, reply='现在觉得精力怎么样？'))
    assert not value.ready
    turns = [SimpleNamespace(message=str(i), response={'reply': str(i)}) for i in range(100)]
    messages = context_messages(turns, None, '这一条')
    assert len(messages) == 14
    assert messages[1]['content'] == '5' and messages[-1]['content'] == '这一条'


@pytest.mark.parametrize('message', ['', '  ', 'x' * 2001])
def test_message_limits(message):
    with pytest.raises(ValidationError):
        MessageInput(request_id=uuid4(), expected_version=0, message=message)


def test_startup_ui_keeps_sliders_and_explicit_confirmation(client):
    response=client.get('/startup')
    assert response.status_code==200
    for marker in ['id="pressure"', 'id="energy"', 'id="chat-form"', 'id="state-form"', 'id="state-history"', 'id="chat-top-tasks"']:
        assert marker in response.text
    assert 'id="recommend-refresh" type="button" class="button primary" disabled' in response.text
