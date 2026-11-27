import json
from uuid import uuid4
import pytest
from app.modules.ai_gateway.adapter import OpenAICompatibleAdapter
from app.modules.ai_gateway.security import AIError
from app.modules.shining_memories.people.analysis_schemas import PersonOutput,CompactPersonOutput
from test_memory_person_analysis import output
from app.modules.shining_memories.people.analysis import validate_result
from app.modules.shining_memories.shared.images import MediaError

def test_compact_and_historical_schema_compatibility():
    data=output().model_dump(mode='json')
    assert CompactPersonOutput.model_validate(data).meaning_label
    old=data|{'meaning_summary':'旧'*300,'meaning_label':'旧'*30}
    assert PersonOutput.model_validate(old)
    with pytest.raises(ValueError):CompactPersonOutput.model_validate(old)
    related={'kind':'task','id':str(uuid4()),'reason':'依据','evidence':[{'source':'person:notes','quote':'依据'}]}
    with pytest.raises(ValueError):CompactPersonOutput.model_validate(data|{'related':[related|{'id':str(uuid4())} for _ in range(4)]})
    with pytest.raises(ValueError):CompactPersonOutput.model_validate(data|{'contact_suggestion':'一\n二\n三\n四'})
    invalid_link=CompactPersonOutput.model_validate(data|{'related':[related]})
    with pytest.raises(MediaError) as error:
        validate_result(invalid_link,{'sources':{'person:precious_moments':'老师给予机会。','person:notes':'依据'},'selected':[]})
    assert error.value.code=='invalid_source'

def test_truncated_even_complete_json_is_rejected_with_private_metrics(caplog):
    caplog.set_level('INFO',logger='adventure_camp')
    sentinel='PRIVATE_CONTENT_SENTINEL'
    response={'choices':[{'finish_reason':'length','message':{'content':json.dumps({'private':sentinel}),'reasoning_content':sentinel}}],
        'usage':{'prompt_tokens':100,'completion_tokens':4096,'total_tokens':4196,'completion_tokens_details':{'reasoning_tokens':4000}}}
    with pytest.raises(AIError) as exc:
        OpenAICompatibleAdapter(lambda *a:response).generate('url','secret','model',[],diagnostics=True,max_tokens=8192,enable_thinking=False)
    assert exc.value.code=='output_truncated' and exc.value.usage['reasoning_tokens']==4000
    assert exc.value.usage['content_length'] and sentinel not in caplog.text
    assert 'person_analysis_output_metrics' in caplog.text and 'secret' not in caplog.text

def test_only_explicit_thinking_option_changes_payload():
    seen=[]
    def provider(url,key,payload):
        seen.append(payload);return {'choices':[{'finish_reason':'stop','message':{'content':'ok'}}],'usage':{'completion_tokens':2}}
    adapter=OpenAICompatibleAdapter(provider)
    assert adapter.generate('url','key','model',[])[1]=={'completion_tokens':2}
    assert 'enable_thinking' not in seen[-1] and seen[-1]['max_tokens']==512
    usage=adapter.generate('url','key','model',[],max_tokens=8192,diagnostics=True,enable_thinking=False)[1]
    assert seen[-1]['enable_thinking'] is False and 'reasoning_tokens' not in usage
