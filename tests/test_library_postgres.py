from datetime import datetime, timezone
from uuid import UUID, uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError
from app.modules.library.models import LibraryLink
from app.modules.library.schemas import Create
from app.modules.library import service
from app.modules.quests.models import MainQuest
from app.modules.tasks.models import Task
from test_distractions_postgres import notes, task_engine

pytestmark=pytest.mark.integration
BASE='/api/library/links'
HEADERS={'Origin':'http://testserver'}


def setup(notes):
    client,sessions,uid,other,app=notes
    q,t,foreign=uuid4(),uuid4(),uuid4()
    with sessions.begin() as db:
        db.add_all([MainQuest(id=q,user_id=uid,title='主线'),MainQuest(id=foreign,user_id=other,title='外部主线')]);db.flush()
        db.add(Task(id=t,user_id=uid,title='副本',main_quest_id=q))
    return client,sessions,uid,other,q,t,foreign,app


def payload(**extra):
    return {'request_id':str(uuid4()),'description':'  文档原始描述  ','url':'https://example.com/docs?q=1#top'}|extra


def test_crud_filters_idempotency_delete_and_restore(notes):
    client,sessions,uid,other,q,t,foreign,app=setup(notes)
    value=payload(main_quest_id=str(q))
    result=client.post(BASE,headers=HEADERS,json=value)
    assert result.status_code==200,result.text
    link=result.json(); url=BASE+'/'+link['id']
    assert link['description']==value['description'] and link['url']==value['url'] and link['click_count']==0
    assert client.post(BASE,headers=HEADERS,json=value).json()['id']==link['id']
    assert client.post(BASE,headers=HEADERS,json=value|{'url':'https://example.com/else'}).status_code==409
    tasklink=client.post(BASE,headers=HEADERS,json=payload(task_id=str(t))).json()
    assert len(client.get(BASE,params={'main_quest_id':str(q)}).json()['items'])==1
    assert len(client.get(BASE,params={'task_id':str(t)}).json()['items'])==1
    updated=client.patch(url,headers=HEADERS,json={'task_id':str(t),'expected_version':1})
    assert updated.status_code==200 and updated.json()['version']==2
    assert client.get(BASE,params={'main_quest_id':str(q)}).json()['items']==[]
    assert client.patch(url,headers=HEADERS,json={'main_quest_id':str(q),'expected_version':1}).status_code==409
    with sessions.begin() as db:
        db.get(Task,t).title='改名后的副本'
    assert client.get(url).json()['target_title']=='改名后的副本'
    with sessions.begin() as db: db.get(MainQuest,q).deleted_at=datetime.now(timezone.utc)
    assert client.get(BASE).json()['items']==[]
    assert client.get(BASE,params={'task_id':str(t)}).status_code==404
    assert not client.get(url).json()['target_available']
    with sessions.begin() as db: db.get(MainQuest,q).deleted_at=None
    assert len(client.get(BASE).json()['items'])==2
    # A fresh connection observes committed bookmarks.
    with sessions() as db: assert db.get(LibraryLink,UUID(link['id'])).url==value['url']
    client.cookies.set('camp_session',str(other))
    assert client.get(BASE).json()['items']==[]
    assert client.get(url).status_code==404
    assert client.request('DELETE',url,headers=HEADERS,json={'expected_version':2}).status_code==404
    client.cookies.set('camp_session',str(uid))
    assert client.request('DELETE',url,headers=HEADERS,json={'expected_version':2}).status_code==200
    assert client.get(url).status_code==404
    with sessions() as db:
        assert db.get(LibraryLink,UUID(link['id'])).deleted_at
        assert db.get(Task,t).deleted_at is None
        assert db.scalar(select(func.sum(LibraryLink.click_count)).where(LibraryLink.user_id==uid))==0


def test_validation_ownership_constraints_and_concurrent_retry(notes):
    client,sessions,uid,other,q,t,foreign,app=setup(notes)
    for values in ({},{'main_quest_id':str(q),'task_id':str(t)}, {'main_quest_id':str(q),'url':'javascript:alert(1)'}, {'main_quest_id':str(q),'description':' '}):
        r=client.post(BASE,headers=HEADERS,json=payload(**values));assert r.status_code==422,r.text
    for target in (foreign,uuid4()):
        assert client.post(BASE,headers=HEADERS,json=payload(main_quest_id=str(target))).status_code==404
    assert client.post(BASE,json=payload(main_quest_id=str(q))).status_code==403
    data=Create(**payload(task_id=str(t)))
    def save():
        with sessions.begin() as db: return service.create(db,uid,data)['id']
    with ThreadPoolExecutor(max_workers=2) as pool: assert len(set(pool.map(lambda _:save(),range(2))))==1
    for values in ({'main_quest_id':foreign},{'main_quest_id':q,'task_id':t},{}):
        with pytest.raises(IntegrityError):
            with sessions.begin() as db:
                db.add(LibraryLink(user_id=uid,description='DB约束',url='https://example.com',create_request_id=uuid4(),create_fingerprint='x'*64,**values));db.flush()
    with pytest.raises(IntegrityError):
        with sessions.begin() as db: db.execute(delete(Task).where(Task.id==t))
    client.cookies.clear()
    assert client.get(BASE).status_code==401
    assert client.post(BASE,headers=HEADERS,json=payload(main_quest_id=str(q))).status_code==401


def test_copy_count_concurrency_idempotence_and_sort(notes):
    from app.modules.library.schemas import Copy
    client,sessions,uid,other,q,t,foreign,app=setup(notes)
    row=client.post(BASE,headers=HEADERS,json=payload(task_id=str(t))).json()
    otherlink=client.post(BASE,headers=HEADERS,json=payload(main_quest_id=str(q))).json()
    url=BASE+'/'+row['id']+'/copies';rid=str(uuid4())
    assert client.get(url).status_code==405
    assert client.post(url,headers=HEADERS,json={'request_id':rid}).json()['click_count']==1
    assert client.post(url,headers=HEADERS,json={'request_id':rid}).json()['click_count']==1
    assert client.post(BASE+'/'+otherlink['id']+'/copies',headers=HEADERS,json={'request_id':rid}).status_code==409
    def add(_):
        with sessions.begin() as db:
            return service.copied(db,uid,UUID(row['id']),Copy(request_id=uuid4()))['click_count']
    with ThreadPoolExecutor(max_workers=3) as pool: assert sorted(pool.map(add,range(3)))==[2,3,4]
    assert client.get(BASE).json()['items'][0]['id']==row['id']
    assert client.get(BASE+'/'+row['id']).json()['version']==1
    assert client.post(url,json={'request_id':str(uuid4())}).status_code==403
    client.cookies.set('camp_session',str(other))
    assert client.post(url,headers=HEADERS,json={'request_id':str(uuid4())}).status_code==404
