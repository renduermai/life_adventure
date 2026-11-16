from uuid import uuid4
import pytest
from sqlalchemy import func, select
from app.modules.startup_chat import planning
from app.modules.startup_chat.models import ChatTurn, Conversation
from app.modules.startup_chat.breakdown_models import BreakdownPlan
from app.modules.startup_chat.session_schemas import Reply
from app.modules.startup_items.models import StartupItem
from app.modules.tasks.models import Task
from app.modules.quests.models import MainQuest
from test_ai_postgres import ai, task_engine, camp

pytestmark = pytest.mark.integration
HEADERS = {'Origin':'http://testserver'}


def reply(**values):
    return Reply(**(dict(reply='现在最困扰你的是什么？',needs_clarification=True,understanding='',completed='',today_goal='',steps=[],minimum_action='')|values))


def payload(uid, **values):
    return dict(owner_id=str(uid),request_id=str(uuid4()),mode='free',message='有点焦虑',history=[],include_tasks=False)|values


def test_free_and_breakdown_context_followup_and_no_writes(ai,monkeypatch):
    camp,settings,app,client=ai
    seen=[]
    def provider(self,uid,purpose,messages,request_id,schema=None,**kwargs):
        assert camp['engine'].pool.checkedout()==0
        seen.append((purpose,messages))
        if purpose=='startup_state':return {'content':'可以先说说此刻最困扰你的事。'}
        if len(seen)<3:return {'content':reply()}
        return {'content':reply(reply='今天只先看一眼目录。',needs_clarification=False,
            understanding='整理工作目录',completed='目录已创建',today_goal='十分钟内看清结构',
            steps=[dict(title='打开目录',detail='只看已有文件',minutes=1,done_when='看到文件列表')],minimum_action='只打开文件夹')}
    monkeypatch.setattr(planning.AIService,'generate',provider)
    context=client.get('/api/startup/chat/context').json()
    assert context['owner_id']==str(camp['user']) and context['target'] is None
    assert client.post('/api/startup/chat/messages',headers=HEADERS,json=payload(camp['user'])).status_code==200
    assert '测试主线' not in seen[0][1][1]['content']
    selected=client.get(f"/api/startup/chat/context?task_type=quest&task_id={camp['quest']}").json()['target']
    assert selected['title']=='测试主线'
    first=payload(camp['user'],mode='breakdown',task_type='quest',task_id=str(camp['quest']),
        message='帮我拆解这件事',state={'pressure':80,'energy':25})
    response=client.post('/api/startup/chat/messages',headers=HEADERS,json=first)
    assert response.status_code==200,response.text
    assert response.json()['response']['needs_clarification']
    second=first|{'request_id':str(uuid4()),'message':'目前已建目录，今天只有十分钟，第一步太难',
        'history':[{'message':first['message'],'reply':response.json()['response']['reply']}]}
    result=client.post('/api/startup/chat/messages',headers=HEADERS,json=second)
    assert result.status_code==200,result.text
    assert result.json()['response']['steps'][0]['done_when']=='看到文件列表'
    assert seen[-1][0]=='breakdown' and '测试主线' in seen[-1][1][1]['content']
    assert '80' in seen[-1][1][1]['content'] and seen[-1][1][-2]['content']==response.json()['response']['reply']
    with camp['sessions']() as db:
        for model in (ChatTurn,Conversation,BreakdownPlan,Task,StartupItem):
            assert db.scalar(select(func.count()).select_from(model).where(model.user_id==camp['user']))==0
        assert db.get(MainQuest,camp['quest']).status=='active'


def test_access_account_binding_and_opt_in_summaries(ai,monkeypatch):
    camp,_,_,client=ai
    seen=[]
    monkeypatch.setattr(planning.AIService,'generate',lambda *args,**kw:(seen.append(args[3]) or {'content':'可以先说说此刻最困扰你的事。'}))
    response=client.post('/api/startup/chat/messages',headers=HEADERS,
        json=payload(camp['user'],include_tasks=True))
    assert response.status_code==200,response.text
    assert '测试主线' in seen[0][1]['content']
    assert client.post('/api/startup/chat/messages',headers=HEADERS,json=payload(camp['other'])).status_code==409
    assert client.get('/api/startup/chat/context?task_type=quest&task_id='+str(uuid4())).status_code==404
    assert client.post('/api/startup/chat/messages',headers=HEADERS,json=payload(camp['user'],mode='breakdown',task_type='task',task_id=str(uuid4()))).status_code==404
    assert len(seen)==1
    assert client.post('/api/startup/chat/messages',json=payload(camp['user'])).status_code==403
    client.cookies.clear()
    assert client.get('/api/startup/chat/context').status_code==401
