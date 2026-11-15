"""Explicit real-provider probe with a temporary synthetic account and task.

Run only with --live. Prints no credentials or private task text; always cleans test rows.
"""
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import delete, select

from app.core.config import Settings
from app.core.database import Database
from app.modules.ai_gateway.models import AIConfig, AICallLog
from app.modules.identity.models import User
from app.modules.quests.models import MainQuest
from app.modules.startup_chat.models import Conversation, ChatTurn
from app.modules.startup_chat.schemas import MessageInput
from app.modules.startup_chat.service import send
from app.modules.startup_state.models import StateCurrent, StateSnapshot
from app.modules.tasks.models import Task


def run():
    assert '--live' in sys.argv, 'Pass --live for a real model call'
    settings = Settings(log_level='ERROR')
    database = Database(settings)
    uid, qid, tid = uuid4(), uuid4(), uuid4()
    try:
        with database.transaction() as db:
            config = db.scalar(select(AIConfig).where(AIConfig.is_default.is_(True),
                AIConfig.deleted_at.is_(None), AIConfig.enabled.is_(True)))
            assert config, 'No enabled model configuration'
            db.add(User(id=uid, username='coach_probe_' + uid.hex,
                password_hash='unused-verification', display_name='合成验收', timezone='Asia/Shanghai'))
            db.flush()
            db.add(AIConfig(user_id=uid, name='合成验收模型', base_url=config.base_url,
                model_id=config.model_id, encrypted_key=config.encrypted_key,
                key_version=config.key_version, key_mask='已设置',
                create_request_id=uuid4(), create_fingerprint='x' * 64,
                enabled=True, is_default=True))
            db.add(MainQuest(id=qid, user_id=uid, title='合成：让桌面清爽',
                description='虚构验收目标', status='active'))
            db.flush()
            db.add(Task(id=tid, user_id=uid, main_quest_id=qid,
                title='合成：把笔放进笔筒', description='桌上有三支笔，先只处理一支。'))
            snapshot = StateSnapshot(user_id=uid, request_id=uuid4(),
                fingerprint='x' * 64, pressure=72, energy=32,
                difficulty='虚构测试：很难开始整理桌面')
            db.add(snapshot)
            db.flush()
            db.add(StateCurrent(user_id=uid, snapshot_id=snapshot.id, generation=1))
        answer = send(database, settings, uid, MessageInput(request_id=uuid4(), expected_version=0,
            selected_target_key='task:' + str(tid),
            message='第一步仍然太难。请把这个任务缩小成一个现在能做的具体动作。'))
        with database.transaction() as db:
            turn = db.scalar(select(ChatTurn).where(ChatTurn.user_id == uid))
            chat = db.scalar(select(Conversation).where(Conversation.user_id == uid))
            log = db.scalar(select(AICallLog).where(AICallLog.user_id == uid))
            assert turn and chat and log
            print('LIVE_COACH', 'status', answer['status'], 'error', answer['error_code'],
                  'selected_persisted', chat.selected_target_key == 'task:' + str(tid),
                  'ready', (answer['response'] or {}).get('ready'),
                  'reply_length', len((answer['response'] or {}).get('reply', '')),
                  'synthetic_reply_escaped', json.dumps((answer['response'] or {}).get('reply', ''), ensure_ascii=True),
                  'usage', log.usage, flush=True)
            assert answer['status'] == 'succeeded'
            assert chat.selected_target_key == 'task:' + str(tid)
            assert answer['response']['reply'].strip()
            assert answer['response']['ready'] is False
            assert '笔' in answer['response']['reply']
            assert db.get(StateCurrent, uid).generation == 1
    finally:
        try:
            with database.transaction() as db:
                for model in (StateCurrent, StateSnapshot, ChatTurn, Conversation,
                              AICallLog, AIConfig, Task, MainQuest, User):
                    db.execute(delete(model).where(model.user_id == uid) if model is not User
                               else delete(User).where(User.id == uid))
        finally:
            database.dispose()


if __name__ == '__main__':
    run()
