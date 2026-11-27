"""Real PostgreSQL persistence for the autosave endpoint reused by V3."""
from uuid import uuid4
import pytest
from test_ai_postgres import ai,task_engine,camp
pytestmark=pytest.mark.integration

def test_position_autosave_persistence_and_conflict(ai):
 camp,_,_,client=ai
 headers={'Origin':'http://testserver'}
 payload={'pressure':80,'energy':25,'difficulty':'','confirmed':True,'expected_generation':0,'request_id':str(uuid4())}
 first=client.post('/api/startup/states',headers=headers,json=payload)
 assert first.status_code==200,first.text
 assert first.json()['quadrant']=='修复区'
 assert client.post('/api/startup/states',headers=headers,json=payload).json()['snapshot_id']==first.json()['snapshot_id']
 read=client.get('/api/startup/current').json()
 assert (read['pressure'],read['energy'])==(80,25)
 second=dict(payload,pressure=20,energy=80,request_id=str(uuid4()),expected_generation=read['generation'])
 assert client.post('/api/startup/states',headers=headers,json=second).json()['quadrant']=='投入区'
 assert client.post('/api/startup/states',headers=headers,json=dict(payload,request_id=str(uuid4()))).status_code==409
 client.cookies.clear()
 assert client.get('/api/startup/current').status_code==401
