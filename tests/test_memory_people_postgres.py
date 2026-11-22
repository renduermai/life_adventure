from datetime import timedelta
from uuid import uuid4
import pytest
from test_distractions_postgres import notes,task_engine
from app.modules.shining_memories.people import service

pytestmark=pytest.mark.integration
BASE='/api/shining-memories/people'
H={'Origin':'http://testserver'}


def test_person_event_dates_permissions_and_versions(notes):
    client,sessions,uid,other,app=notes
    with sessions() as db:today=service.today(db,uid)
    data={'request_id':str(uuid4()),'name':'合成老师','relationship':'老师','manual_contact_date':str(today-timedelta(days=500))}
    r=client.post(BASE,headers=H,json=data);assert r.status_code==200,r.text
    p=r.json();url=BASE+'/'+p['id'];assert client.post(BASE,headers=H,json=data).json()['id']==p['id']
    def event(days,actual):return client.post(url+'/events',headers=H,json={'request_id':str(uuid4()),'event_date':str(today-timedelta(days=days)),'content':'合成事件原文','is_actual_contact':actual})
    assert event(1,False).status_code==200
    assert client.get(url).json()['last_contact_date']==data['manual_contact_date']
    actual=event(10,True).json();assert client.get(url).json()['last_contact_date']==str(today-timedelta(days=10))
    assert event(100,True).status_code==200
    assert client.get(url).json()['last_contact_date']==str(today-timedelta(days=10))
    assert client.request('DELETE',url+'/events/'+actual['id'],headers=H,json={'expected_version':1}).status_code==200
    assert client.get(url).json()['last_contact_date']==str(today-timedelta(days=100))
    assert event(-1,True).status_code==422
    assert client.patch(url,headers=H,json={k:v for k,v in data.items() if k!='request_id'}|{'expected_version':1}).status_code==409
    client.cookies.set('camp_session',str(other));assert client.get(url).status_code==404
    client.cookies.set('camp_session',str(uid));p=client.get(url).json()
    assert client.request('DELETE',url,headers=H,json={'expected_version':p['version']}).status_code==200
    assert client.get(url).status_code==404
