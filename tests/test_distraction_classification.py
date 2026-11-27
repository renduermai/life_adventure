from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.modules.distractions.classification_service import Result, partition
from app.modules.ai_gateway.security import AIError


def test_complete_partition_and_invalid_ids():
    a,b = uuid4(),uuid4()
    valid = Result(groups=[dict(category='求职',summary='担心能力',note_ids=[a])],unclassified_note_ids=[b])
    partition(valid,[a,b])
    for ids in ([a,a],[a],[a,uuid4()]):
        with pytest.raises(AIError):
            partition(Result(groups=[],unclassified_note_ids=ids),[a,b])
    with pytest.raises(ValidationError):
        Result(groups=[dict(category='求职',summary='担心能力')],unclassified_note_ids=[])
