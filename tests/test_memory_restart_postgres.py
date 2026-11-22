"""Two actual fresh Python server processes read the same isolated PostgreSQL data."""
import json,os,socket,subprocess,sys,time,urllib.request
from uuid import uuid4
from sqlalchemy import text
import pytest
from app.core.config import ROOT
from test_distractions_postgres import notes,task_engine

pytestmark=pytest.mark.integration

def test_two_process_restarts_read_saved_records(notes):
    client,sessions,uid,other,app=notes
    headers={'Origin':'http://testserver'}
    paths={}
    for kind,fields in [('people',{'name':'合成人物','relationship':'朋友'}),('items',{'name':'合成物品','purchase_date':'2026-01-01','purchase_price':'50'}),('wishes',{'name':'合成心愿','price':'100'})]:
        r=client.post('/api/shining-memories/'+kind,headers=headers,json={'request_id':str(uuid4()),**fields})
        assert r.status_code==200,r.text
        paths[kind]='/api/shining-memories/'+kind+'/'+r.json()['id']
    with sessions() as db:schema=db.execute(text('SELECT current_schema()')).scalar_one()
    assert schema.startswith('ac_tasks_test_')
    engine=sessions.kw['bind'];env=os.environ.copy()
    env['AC_TEST_DB']=engine.url.render_as_string(hide_password=False)
    env['AC_TEST_SCHEMA']=schema;env['AC_TEST_MARKER']=uuid4().hex
    code='''import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import create_app
from app.core.config import Settings
from fastapi import Request,HTTPException
import uvicorn
engine=create_engine(os.environ['AC_TEST_DB'],hide_parameters=True,connect_args={'options':'-c search_path='+os.environ['AC_TEST_SCHEMA']})
app=create_app(Settings(_env_file=None))
app.state.database.engine=engine
app.state.database.sessions=sessionmaker(engine,expire_on_commit=False)
@app.get('/acceptance-probe')
def probe():return {'marker':os.environ['AC_TEST_MARKER']}
@app.post('/acceptance-stop')
def stop(request:Request):
 if request.headers.get('X-Acceptance-Marker')!=os.environ['AC_TEST_MARKER']:raise HTTPException(403)
 server.should_exit=True
 return {'stopping':True}
server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=int(os.environ['AC_TEST_PORT']),log_level='error',access_log=False))
server.run()
'''
    for _ in range(2):
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        env['AC_TEST_PORT']=str(port)
        process=subprocess.Popen([sys.executable,'-c',code],env=env,cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            ready=False
            for attempt in range(100):
                if process.poll() is not None:break
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/acceptance-probe',timeout=.5) as r:
                        ready=json.load(r)['marker']==env['AC_TEST_MARKER']
                        if ready:break
                except (OSError,ValueError):pass
                time.sleep(.1)
            assert ready,'Isolated acceptance server did not start'
            for kind,path in paths.items():
                request=urllib.request.Request(f'http://127.0.0.1:{port}'+path,headers={'Cookie':'camp_session='+str(uid)})
                with urllib.request.urlopen(request,timeout=15) as r:data=json.load(r)
                assert data['name']=={'people':'合成人物','items':'合成物品','wishes':'合成心愿'}[kind]
        finally:
            if process.poll() is None:
                try:
                    request=urllib.request.Request(f'http://127.0.0.1:{port}/acceptance-stop',data=b'',headers={'X-Acceptance-Marker':env['AC_TEST_MARKER']},method='POST')
                    with urllib.request.urlopen(request,timeout=3):pass
                    process.wait(timeout=10)
                except (OSError,subprocess.TimeoutExpired):
                    if process.poll() is None:
                        # Only the process tree created by this test, never port owners.
                        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    process.wait(timeout=10)
