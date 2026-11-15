from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.modules.startup_chat.breakdown_schemas import Advice, Step
from app.modules.startup_chat.breakdown_service import similar


def advice():
    return dict(reply='先做一个小动作。',steps=[dict(title='打开项目',detail='打开现有项目目录',minutes=2,done_when='看到目录'),dict(title='运行一个样例',detail='使用已有样例',minutes=5,done_when='看到输出')],minimum_index=0,state_advice=None)


@pytest.mark.parametrize('change',[{'minimum_index':2},{'steps':[]},{'steps':[advice()['steps'][0]]*6},{'minimum_index':True}])
def test_plan_schema_bounds(change):
    with pytest.raises(ValidationError):Advice(**(advice()|change))


@pytest.mark.parametrize('minutes',[0,241,True,'5'])
def test_estimated_minutes_are_bounded_integers(minutes):
    with pytest.raises(ValidationError):Step(**(advice()['steps'][0]|{'minutes':minutes}))


def test_duplicate_normalization():
    assert similar(' Open Project! ', 'ＯＰＥＮ project')
    assert similar('整理 桌面。','整理桌面')
    assert not similar('打开目录','跑一个样例')


def test_breakdown_panel_and_scripts(client):
    response=client.get('/startup?task_type=task&task_id='+str(uuid4()))
    assert response.status_code==200
    for marker in ['breakdown-editor','breakdown-confirm','breakdown-feedback','breakdown-history','breakdown-start']:
        assert 'id="'+marker+'"' in response.text
