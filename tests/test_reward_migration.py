"""Verify online migration backfills only current completion rounds."""
import os
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from app.core.config import ROOT, postgres_url
from app.modules.identity.models import User
from app.modules.tasks.models import Task, TaskEvent

@pytest.mark.integration
def test_reward_migration_backfills_completed_tasks():
    url=os.environ.get('TEST_DATABASE_URL')
    if not url: pytest.skip('TEST_DATABASE_URL not configured')
    engine=create_engine(postgres_url(url),hide_parameters=True,connect_args={'connect_timeout':5})
    schema='ac_rewards_test_'+uuid4().hex
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            config=Config(str(ROOT/'alembic.ini')); config.attributes['connection']=conn
            command.upgrade(config,'0006_activity')
            with Session(bind=conn,join_transaction_mode='create_savepoint') as db:
                user=User(id=uuid4(),username='test_reward_'+uuid4().hex,password_hash='unused',display_name='test',timezone='UTC')
                db.add(user); db.flush()
                for deleted in (False,True):
                    task=Task(id=uuid4(),user_id=user.id,title='finished',status='completed',completed_at=datetime.now(timezone.utc),completion_round=1,version=1,deleted_at=datetime.now(timezone.utc) if deleted else None)
                    db.add(task); db.flush()
                    db.add(TaskEvent(id=uuid4(),user_id=user.id,task_id=task.id,kind='completed',completion_round=1,payload={}))
                db.add(Task(id=uuid4(),user_id=user.id,title='pending',status='todo',completion_round=0,version=1))
                db.commit()
            command.upgrade(config,'head'); command.upgrade(config,'head')
            count,xp,coins=conn.execute(text('SELECT count(*),sum(xp_delta),sum(coin_delta) FROM reward_entries')).one()
            assert (count,xp,coins)==(2,20,10)
    finally:
        with engine.begin() as conn: conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
