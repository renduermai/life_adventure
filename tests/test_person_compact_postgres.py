import json,os
from uuid import uuid4,UUID
from datetime import date
import pytest
from sqlalchemy import select
from cryptography.fernet import Fernet
from app.core.config import Settings,load_settings
from app.modules.ai_gateway import service as gateway
from app.modules.ai_gateway.models import AIConfig,AICallLog
from app.modules.ai_gateway.security import encrypt,AIError
from app.modules.shining_memories.people.analysis_schemas import CompactPersonOutput,PersonOutput
from test_distractions_postgres import notes,task_engine
from test_memory_person_analysis_postgres import setup,preview,run
from test_memory_person_analysis import output

pytestmark=pytest.mark.integration

def test_actual_gateway_policy_and_truncated_usage_keeps_old(notes,monkeypatch):
    client,sessions,uid,other,app,person,url=setup(notes)
    settings=Settings(_env_file=None,ai_encryption_keys=Fernet.generate_key().decode());app.state.settings=settings
    with sessions.begin() as db:
        config=db.scalar(select(AIConfig).where(AIConfig.user_id==uid));config.encrypted_key=encrypt(settings,'synthetic-key-only')
        config.base_url='https://synthetic.cn-beijing.maas.aliyuncs.com/compatible-mode/v1';config.model_id='deepseek-v4.1-flash'
    seen=[]
    def provider(url,key,payload,**kwargs):
        seen.append(payload)
        return {'choices':[{'finish_reason':'stop','message':{'content':output().model_dump_json()}}],'usage':{'prompt_tokens':200,'completion_tokens':300,'total_tokens':500,'completion_tokens_details':{'reasoning_tokens':0}}}
    monkeypatch.setattr(gateway,'post_json',provider)
    monkeypatch.setattr(gateway.AIService,'generate',REAL_GENERATE)
    p=preview(client,url);r=run(client,url,p);assert r.status_code==200,r.text
    assert seen[0]['max_tokens']==8192 and seen[0]['enable_thinking'] is False
    with sessions() as db:
        log=db.scalar(select(AICallLog).where(AICallLog.user_id==uid));assert log.usage['reasoning_tokens']==0
    # Source edit invalidates cache; a truncated replacement must retain the old success.
    fields={k:person[k] for k in ('name','relationship','precious_moments','manual_contact_date','contact_preference','notes')}
    assert client.patch(url,headers={'Origin':'http://testserver'},json=fields|{'expected_version':1,'notes':'合成新增记录'}).status_code==200
    def truncated(*args,**kwargs):return {'choices':[{'finish_reason':'length','message':{'content':output().model_dump_json()}}],'usage':{'completion_tokens':8192,'completion_tokens_details':{'reasoning_tokens':0}}}
    monkeypatch.setattr(gateway,'post_json',truncated)
    assert run(client,url,preview(client,url)).status_code==502
    saved=client.get(url+'/analysis').json();assert saved['analysis']['meaning_label']==output().meaning_label
    assert saved['last_attempt']['error_code']=='output_truncated'
    with sessions() as db:
        failed=db.scalar(select(AICallLog).where(AICallLog.user_id==uid,AICallLog.error_code=='output_truncated'))
        assert failed.usage['completion_tokens']==8192
    monkeypatch.setattr(gateway,'post_json',provider)
    for purpose,budget in [('breakdown',1536),('task_analysis',1536),('startup_state',1536),('wish_category',1536),('distraction_classification',4096),('connection_test',512)]:
        gateway.AIService(app.state.database,settings).generate(uid,purpose,[{'role':'user','content':'合成兼容性检查'}],uuid4())
        assert seen[-1]['max_tokens']==budget and 'enable_thinking' not in seen[-1]

REAL_GENERATE=gateway.AIService.generate

@pytest.mark.skipif(os.environ.get('RUN_PERSON_COMPACT_LIVE')!='1',reason='真实人物精简输出测试需显式启用')
def test_live_baseline_and_three_compact_cases(notes,monkeypatch):
    from app.core.database import Database
    from app.modules.ai_gateway.security import decrypt
    from app.modules.ai_gateway.schemas import CreateConfig
    from app.modules.ai_gateway.adapter import OpenAICompatibleAdapter
    from app.modules.quests.models import MainQuest
    from app.modules.tasks.models import Task
    from app.modules.distractions.models import DistractionNote
    from app.modules.shining_memories.people.models import MemoryPersonEvent
    from app.modules.shining_memories.people.analysis import context,validate_result
    from app.modules.shining_memories.people.analysis_schemas import Scope
    client,sessions,uid,other,app=notes;settings=load_settings();app.state.settings=settings
    source=Database(settings)
    try:
        with source.transaction() as db:
            cfg=db.scalar(select(AIConfig).where(AIConfig.is_default.is_(True),AIConfig.enabled.is_(True),AIConfig.deleted_at.is_(None)))
            assert cfg and cfg.model_id=='deepseek-v4.1-flash'
            config_values={'base_url':cfg.base_url,'model_id':cfg.model_id,'api_key':decrypt(settings,cfg.encrypted_key)}
    finally:source.dispose()
    with sessions.begin() as db:
        cfg=gateway.create_config(db,uid,CreateConfig(request_id=uuid4(),name='合成人物精简验收',**config_values),settings);cfg.is_default=True
    monkeypatch.setattr(gateway.AIService,'generate',REAL_GENERATE)
    endpoint='/api/shining-memories/people';headers={'Origin':'http://testserver'}
    short='他在我经验不足时给予练习机会，并耐心提供建议。我愿意向他汇报最近的练习进展。'
    for case in ('short','long','linked'):
        r=client.post(endpoint,headers=headers,json={'request_id':str(uuid4()),'name':'合成导师','relationship':'老师','precious_moments':short,'contact_preference':'willing','notes':'有时沟通节奏太快让我感到压力，希望联系前先准备提纲。'})
        assert r.status_code==200
        pid=UUID(r.json()['id']);url=endpoint+'/'+str(pid);scope={}
        with sessions.begin() as db:
            if case!='short':
                for i in range(10):db.add(MemoryPersonEvent(person_id=pid,user_id=uid,event_date=date(2026,1,1),content=f'合成事件{i}：我们讨论练习项目，老师鼓励我先完成最小功能。'+('我记录了进展和仍需请教的问题。'*20),is_actual_contact=False,create_request_id=uuid4(),create_fingerprint='x'*64))
            if case=='linked':
                qs=[];ts=[];ns=[]
                for i in range(3):
                    qid,tid,nid=uuid4(),uuid4(),uuid4();qs.append(qid);ts.append(tid);ns.append(nid)
                    db.add(MainQuest(id=qid,user_id=uid,title=f'合成目标{i}',description='练习独立交付Python项目'))
                    db.add(Task(id=tid,user_id=uid,title=f'合成副本{i}',description='完成一个最小功能'))
                    db.add(DistractionNote(id=nid,user_id=uid,content=f'合成杂念{i}：担心自己经验不足，但愿意从最小功能开始。',create_request_id=uuid4(),create_fingerprint='n'*64))
                scope={'include_tasks':True,'include_notes':True,'quest_ids':list(map(str,qs)),'task_ids':list(map(str,ts)),'note_ids':list(map(str,ns))}
        if case=='short':
            # Comparable synthetic baseline: old budget/schema, provider default thinking.
            with sessions() as db:payload,_,_=context(db,uid,pid,Scope())
            try:
                _,usage=OpenAICompatibleAdapter(gateway.post_json).generate(config_values['base_url'],config_values['api_key'],config_values['model_id'],
                    [{'role':'system','content':'根据提供的人物经历生成完整的结构化人物分析，所有判断需要原文依据，关联只能使用提供ID。'},
                     {'role':'user','content':json.dumps(payload,ensure_ascii=False)}],PersonOutput,max_tokens=4096,json_mode=True,diagnostics=True)
                print('SYNTHETIC_BASELINE',json.dumps(usage,sort_keys=True))
            except AIError as error:print('SYNTHETIC_BASELINE',error.code,json.dumps(getattr(error,'usage',None),sort_keys=True))
        p=preview(client,url,scope);r=run(client,url,p,scope)
        assert r.status_code==200,r.text
        CompactPersonOutput.model_validate(r.json()['analysis']) if not r.json()['analysis']['related'] else None
        with sessions() as db:
            payload,_,_=context(db,uid,pid,Scope.model_validate(scope))
            # GET adds href for display; validate against the persisted model result instead.
            from app.modules.shining_memories.people.analysis_models import PersonAnalysis
            record=db.scalar(select(PersonAnalysis).where(PersonAnalysis.person_id==pid,PersonAnalysis.state=='succeeded'))
            result=CompactPersonOutput.model_validate(record.result);validate_result(result,payload)
            log=db.scalar(select(AICallLog).where(AICallLog.user_id==uid).order_by(AICallLog.started_at.desc()).limit(1))
            assert log.usage['finish_reason']=='stop' and log.usage['thinking_enabled'] is False
            print('COMPACT_CASE',case,json.dumps(log.usage,sort_keys=True))
        assert client.get(url+'/analysis').status_code==200
