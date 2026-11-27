from uuid import uuid4
from datetime import datetime, timedelta, timezone
from app.modules.identity.models import LoginSession
from app.modules.identity.service import token_hash
import pytest
from sqlalchemy import select
from app.modules.tasks.models import Task
from app.modules.quests.models import MainQuest
from test_ai_postgres import ai, task_engine, camp

pytestmark=pytest.mark.integration

def test_manual_focus_persistence_and_isolation(ai):
    camp,settings,app,client=ai
    with camp['sessions'].begin() as db:
        db.add(LoginSession(user_id=camp['other'],token_hash=token_hash(str(camp['other'])),expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
        task=Task(user_id=camp['user'],title='manual label test');db.add(task);db.flush();tid=task.id
    headers={'Origin':'http://testserver'}
    for kind,identifier,model in [('quests',camp['quest'],MainQuest),('tasks',tid,Task)]:
        url=f'/api/{kind}/{identifier}/manual-focus'
        version=1
        for value in ['recommended','normal','not_recommended','deferred','routine_practice']:
            response=client.patch(url,headers=headers,json={'status':value,'expected_version':version})
            assert response.status_code==200,response.text
            version+=1
            with camp['sessions']() as db:
                row=db.get(model,identifier)
                assert row.manual_focus_status==value and row.manual_focus_version==version
                assert row.status==('active' if kind=='quests' else 'todo')
                if kind=='tasks':assert row.version==1 and row.priority=='normal'
        assert client.patch(url,headers=headers,json={'status':'deferred','expected_version':1}).status_code==409
        assert client.patch(url,headers=headers,json={'status':'bad','expected_version':version}).status_code==422
        assert client.patch(url,json={'status':'normal','expected_version':version}).status_code==403
        client.cookies.set('camp_session',str(camp['other']))
        assert client.patch(url,headers=headers,json={'status':'normal','expected_version':version}).status_code==404
        client.cookies.set('camp_session',str(camp['user']))
    for path in ['/quests',f"/quests/{camp['quest']}",'/tasks',f'/tasks/{tid}']:
        response=client.get(path)
        assert response.status_code==200
        assert 'data-focus-select' in response.text and 'routine_practice' in response.text
        assert 'js/recommendation_widgets.js' not in response.text
        assert 'data-breakdown-link' in response.text
