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


def test_v3_manual_label_item_analysis_session_and_export_coexist(ai,monkeypatch):
    import io,json,zipfile
    from app.modules.startup_items.analysis import Classification
    camp,_,_,client=ai
    from test_ai_postgres import make
    make(ai)
    with camp['sessions'].begin() as db:
        task=Task(user_id=camp['user'],title='练习项目',description='已建好目录，今天看一眼',main_quest_id=camp['quest'])
        db.add(task);db.flush();tid=task.id
    label=client.patch(f'/api/tasks/{tid}/manual-focus',headers=HEADERS,json={'status':'routine_practice','expected_version':1})
    assert label.status_code==200
    created=client.post('/api/startup/items',headers=HEADERS,json={'request_id':str(uuid4()),'description':'整理桌面',
        'importance':35,'urgency':30,'progress':'已经整理一半'}).json()
    def provider(self,uid,purpose,messages,request_id,schema=None,**kwargs):
        if purpose=='task_analysis':
            item=json.loads(messages[-1]['content'])
            return {'content':Classification(item_id=item['item_id'],keyword='整理桌面',quadrant='修复区',reason='适合轻量启动',action='先挪一支笔')}
        return {'content':reply(needs_clarification=False,reply='只打开目录即可。',steps=[dict(title='打开目录',detail='先看一眼',minutes=1,done_when='看到列表')],minimum_action='只打开目录')}
    monkeypatch.setattr(planning.AIService,'generate',provider)
    classified=client.post('/api/startup/items/'+created['id']+'/analyze',headers=HEADERS,json={'request_id':str(uuid4())})
    assert classified.json()['item']['analysis']['result']['quadrant']=='修复区'
    state=client.post('/api/startup/states',headers=HEADERS,json={'pressure':80,'energy':25,'confirmed':True,
        'expected_generation':0,'request_id':str(uuid4())})
    assert state.json()['quadrant']=='修复区'
    answer=client.post('/api/startup/chat/messages',headers=HEADERS,json=payload(camp['user'],mode='breakdown',task_type='task',task_id=str(tid),message='只有一分钟，帮我再拆小一点'))
    assert answer.status_code==200,answer.text
    assert client.post('/api/startup/items/'+created['id']+'/analyze',headers=HEADERS,json={'request_id':str(uuid4())}).json()['cached']
    exported=client.post('/data/export',headers=HEADERS)
    assert exported.status_code==200
    data=json.loads(zipfile.ZipFile(io.BytesIO(exported.content)).read('adventure-camp.json'))
    assert data['tables']['startup_items'][0]['analysis_result']['quadrant']=='修复区'
    assert next(t for t in data['tables']['tasks'] if t['id']==str(tid))['manual_focus_status']=='routine_practice'
    with camp['sessions']() as db:
        task=db.get(Task,tid)
        assert task.status=='todo' and task.version==1 and task.manual_focus_status=='routine_practice'
        assert db.scalar(select(func.count()).select_from(Task).where(Task.user_id==camp['user']))==1
        assert db.scalar(select(func.count()).select_from(StartupItem).where(StartupItem.user_id==camp['user']))==1
