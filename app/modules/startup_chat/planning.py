"""Reusable action-step contract and structured model generation, without task writes."""
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from app.modules.ai_gateway.service import AIService


class Step(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=160)
    detail: str = Field(max_length=600)
    minutes: StrictInt = Field(ge=1, le=240)
    done_when: str = Field(min_length=1, max_length=200)


def generate_structured(database, settings, uid, purpose, messages, request_id, schema, *, session=False):
    answer = AIService(database, settings).generate(uid, purpose, messages, request_id, schema, **({'json_mode':True,'timeout_seconds':90} if session else {}))
    answer['content'] = schema.model_validate(answer['content'])
    return answer
