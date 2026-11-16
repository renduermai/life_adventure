from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.modules.distractions.schemas import Create, Delete


@pytest.mark.parametrize('value', ['', ' \n\t', 'x' * 5001, 123, None, 'a\x00b'])
def test_invalid_original(value):
    with pytest.raises(ValidationError):
        Create(request_id=uuid4(), content=value)


def test_original_preserved_and_strict_contract():
    value = '  我担心进度。\n\n保留原文  '
    assert Create(request_id=uuid4(), content=value).content == value
    assert len(Create(request_id=uuid4(), content='字' * 5000).content) == 5000
    with pytest.raises(ValidationError):
        Create(request_id=uuid4(), content=value, task_id=str(uuid4()))
    with pytest.raises(ValidationError):
        Delete(expected_version=True)
