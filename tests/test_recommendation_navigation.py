from uuid import uuid4
import pytest
from app.core.config import ROOT
from fastapi.templating import Jinja2Templates


@pytest.mark.parametrize('kind', ['quest','task'])
def test_breakdown_link_preserves_target_and_chat_anchor(kind):
    target=uuid4()
    template=Jinja2Templates(directory=ROOT/'app/templates').env.get_template('recommendation_widget.html')
    html=template.module.recommendation(kind,target)
    assert f'task_type={kind}&amp;task_id={target}#chat' in html
    assert '未评估' in html
    assert f'data-recommendation-key="{kind}:{target}"' in html


def test_context_masks_other_owners(monkeypatch):
    from app.modules.startup_state import context
    from app.modules.ai_gateway.security import AIError
    monkeypatch.setattr(context,'get_quest',lambda *args:None)
    with pytest.raises(AIError,match='不可访问') as exc:
        context.target_context(None,uuid4(),'quest',uuid4())
    assert exc.value.status==404
