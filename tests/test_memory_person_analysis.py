from datetime import date,timedelta
from app.modules.shining_memories.people.analysis import score,validate_result
from app.modules.shining_memories.people.analysis_schemas import PersonOutput
from app.modules.shining_memories.shared.images import MediaError
import pytest


def output():
    yes={'level':'strong','reason':'曾给予机会','evidence':[{'source':'person:precious_moments','quote':'给予机会'}]}
    no={'level':'none','reason':'暂无依据','evidence':[]}
    return PersonOutput.model_validate({'meaning_label':'给予机会的老师','meaning_summary':'老师曾给予机会。',
        'positive_factors':['给予机会'],'meaning':yes,'topic':no,'goal':no,
        'negative':{'severity':'none','reason':'暂无负面记录','evidence':[]},'related':[],'contact_suggestion':'愿意时可以简短表达感谢。'})


def test_scoring_boundaries_and_evidence():
    result=output();today=date(2026,11,22)
    assert score(result,'willing',None,today)['score']==45
    assert score(result,'willing',today-timedelta(days=400),today)['score']==60
    assert score(result,'hesitant',today-timedelta(days=400),today)['score']==40
    assert score(result,'no_contact',None,today)['status']=='excluded'
    result.negative.severity='defer';assert score(result,'willing',None,today)['status']=='deferred'
    result=output();validate_result(result,{'sources':{'person:precious_moments':'老师给予机会。'},'selected':[]})
    with pytest.raises(MediaError):validate_result(result,{'sources':{'person:precious_moments':'没有这段内容'},'selected':[]})
    result.meaning.level='none';assert score(result,'willing',today-timedelta(days=1000),today)['score'] is None
