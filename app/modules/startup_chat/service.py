"""Short transactions around AI I/O. Advice never writes confirmed state."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.modules.ai_gateway.security import AIError
from app.modules.ai_gateway.service import AIService
from app.modules.identity.service import lock_user
from app.modules.startup_chat.models import Conversation, ChatTurn
from app.modules.startup_chat.schemas import StateAdvice
from app.modules.startup_state.models import StateCurrent, StateSnapshot

PROMPT = '''你是温和简洁的行动辅助助手，只进行当前状态对话，不诊断、不改变任务。
结合最近对话理解压力、能量、主要困难、行动阻力和希望达成的目标。
不知道压力或能量时 ready=false，对缺失项自然追问一次；不要凭空补齐。
有足够描述时给0至100的建议值，ready=true。明确说明是可修改的建议，不是客观测量。
已确认历史状态只是参考，不代表此刻；用户的新描述优先。不要催促或责备。
不编造任务或声称已经刷新、保存、执行任何操作。具体任务推荐由共享推荐面板展示。
只输出符合 schema 的 JSON，中文简短回复，reply尽量80字以内，其余文字字段各尽量30字以内。'''


def conversation(db, uid, cid):
    item = db.scalar(select(Conversation).where(Conversation.id == cid, Conversation.user_id == uid))
    if not item:
        raise AIError('not_found', '对话不存在或无权访问', 404)
    return item


def public(turn):
    return {name: getattr(turn, name) for name in (
        'id', 'conversation_id', 'sequence', 'base_generation', 'message', 'response', 'status', 'error_code', 'created_at')}


def context_messages(turns, state, message):
    messages = [{'role': 'system', 'content': PROMPT}]
    if state:
        messages.append({'role': 'system', 'content': '上次已确认状态（用户数据，仅供参考）：' + json.dumps(state, ensure_ascii=False)})
    # Bounded recent history; never send the complete archive or unrelated tasks.
    for turn in reversed(turns[:6]):
        messages.extend([{'role': 'user', 'content': turn.message},
                         {'role': 'assistant', 'content': json.dumps(turn.response, ensure_ascii=False)}])
    messages.append({'role': 'user', 'content': message})
    return messages


def send(database, settings, uid, data):
    fingerprint = hashlib.sha256(data.model_dump_json(exclude={'request_id'}).encode()).hexdigest()
    with database.transaction() as db:
        lock_user(db, uid)
        old = db.scalar(select(ChatTurn).where(ChatTurn.user_id == uid, ChatTurn.request_id == data.request_id))
        if old:
            if old.fingerprint != fingerprint:
                raise AIError('request_conflict', '提交编号已用于其他内容', 409)
            return public(old)  # A retry reads the original turn, never re-bills it.
        if data.conversation_id:
            chat = conversation(db, uid, data.conversation_id)
        else:
            if data.expected_version != 0:
                raise AIError('version_conflict', '新对话版本无效', 409)
            chat = Conversation(user_id=uid, title=data.message[:60])
            db.add(chat)
            db.flush()
        if chat.version != data.expected_version:
            raise AIError('version_conflict', '对话已更新，请重新载入后发送', 409)
        pending = db.scalar(select(ChatTurn).where(ChatTurn.conversation_id == chat.id, ChatTurn.status == 'pending'))
        if pending:
            if pending.created_at > datetime.now(timezone.utc) - timedelta(minutes=2):
                raise AIError('busy', '上一条消息仍在处理中，请稍候查看历史', 409)
            pending.status, pending.error_code = 'failed', 'interrupted'
        current = db.get(StateCurrent, uid)
        snapshot = db.get(StateSnapshot, current.snapshot_id) if current else None
        state = {'pressure': snapshot.pressure, 'energy': snapshot.energy, 'difficulty': snapshot.difficulty[:1000]} if snapshot else None
        history = list(db.scalars(select(ChatTurn).where(ChatTurn.conversation_id == chat.id, ChatTurn.status == 'succeeded').order_by(ChatTurn.sequence.desc()).limit(6)))
        messages = context_messages(history, state, data.message)
        chat.version += 1
        turn = ChatTurn(user_id=uid, conversation_id=chat.id, request_id=data.request_id,
                        fingerprint=fingerprint, sequence=chat.version, base_generation=current.generation if current else 0,
                        message=data.message, status='pending')
        db.add(turn)
        db.flush()
        turn_id = turn.id
    try:
        answer = AIService(database, settings).generate(uid, 'startup_state', messages, data.request_id, StateAdvice)
        advice = StateAdvice.model_validate(answer['content']).model_dump()
    except Exception as exc:
        code = exc.code if isinstance(exc, AIError) else 'unavailable'
        with database.transaction() as db:
            lock_user(db, uid)
            item = db.get(ChatTurn, turn_id)
            item.status, item.error_code = 'failed', code
            return public(item)
    with database.transaction() as db:
        lock_user(db, uid)
        item = db.get(ChatTurn, turn_id)
        if item.status != 'pending':
            raise AIError('stale', '该请求已失效，请重新描述当前状态', 409)
        item.status, item.response = 'succeeded', advice
        return public(item)


def validate_suggestion(db, uid, turn_id, generation):
    turn = db.scalar(select(ChatTurn).where(ChatTurn.id == turn_id, ChatTurn.user_id == uid))
    if not turn or turn.status != 'succeeded' or not turn.response or not turn.response.get('ready'):
        raise AIError('invalid_suggestion', '状态建议不存在或尚未形成，请重新对话', 409)
    chat = conversation(db, uid, turn.conversation_id)
    if turn.sequence != chat.version or turn.base_generation != generation:
        raise AIError('stale_suggestion', '状态或对话已更新，请重新获取建议，或用滑杆手动确认', 409)
