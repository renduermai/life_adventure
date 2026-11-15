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
from app.modules.startup_state.context import target_context
from app.modules.task_recommendation.service import candidates, current_view

PROMPT = '''你是温和简洁的状态教练，用真实任务帮助用户找到容易开始的动作；不诊断、不改变任务。
结合最新描述、已确认状态和提供的有效任务摘要。选中的任务优先于历史对话中的旧目标。
只有用户描述了新的当前状态且信息足够时，给出0至100的可修改建议值，ready=true；缺少压力或能量就自然追问，不猜数值。
用户已有确认状态、此轮只是讨论任务时，沿用确认状态，ready=false，pressure和energy为null，不要求重复确认。
根据已保存的推荐等级与理由解释建议；未分析或过期时明确说尚无当前评价，不编造等级、任务或坐标。
若用户说“第一步仍然太难”，把选中任务缩小为一个具体、低门槛、无需立即完成全任务的动作，并在reply中说清楚。
用户的新描述优先于历史；不催促、不声称已经刷新、保存、拆解或执行任何操作。
只输出符合 schema 的 JSON，中文简短回复，reply尽量120字以内，其余文字字段各尽量30字以内。'''


def conversation(db, uid, cid):
    item = db.scalar(select(Conversation).where(Conversation.id == cid, Conversation.user_id == uid))
    if not item:
        raise AIError('not_found', '对话不存在或无权访问', 404)
    return item


def public(turn):
    return {name: getattr(turn, name) for name in (
        'id', 'conversation_id', 'sequence', 'base_generation', 'message', 'response', 'status', 'error_code', 'created_at')}


def context_messages(turns, state, message, task_context=None):
    messages = [{'role': 'system', 'content': PROMPT}]
    if state:
        messages.append({'role': 'system', 'content': '上次已确认状态（用户数据，仅供参考）：' + json.dumps(state, ensure_ascii=False)})
    if task_context is not None:
        messages.append({'role': 'system', 'content': '当前用户有效任务与已保存推荐（仅供本次对话）：' + json.dumps(task_context, ensure_ascii=False)})
    # Bounded recent history; never send the complete archive or unrelated tasks.
    for turn in reversed(turns[:6]):
        messages.extend([{'role': 'user', 'content': turn.message},
                         {'role': 'assistant', 'content': json.dumps(turn.response, ensure_ascii=False)}])
    messages.append({'role': 'user', 'content': message})
    return messages


def task_context_for_chat(db, uid, selected_key):
    live, _ = candidates(db, uid)
    if selected_key and selected_key not in live:
        raise AIError('invalid_target', '所选任务已不可用，请重新选择', 409)
    view = current_view(db, uid)
    evaluated = {item['key']: item for item in view['items']}
    quest_titles = {str(task['id']): task['title'] for task in live.values() if task['kind'] == 'quest'}
    summaries = []
    for key, task in list(live.items())[:20]:
        rating = evaluated.get(key)
        valid = rating and not rating['stale'] and rating['analysis_status'] == 'analyzed'
        summaries.append({'key': key, 'type': task['kind'], 'title': task['title'][:100],
                          'description': (task['description'] or '')[:220],
                          'main_quest': task['title'] if task['kind'] == 'quest' else
                          quest_titles.get(task['context']['main_quest_id'], '独立副本'),
                          'status': task['context']['status'],
                          'level': rating['level'] if valid else None,
                          'reason': rating['reason'] if valid else '当前尚未分析或评价已过期'})
    selected = None
    if selected_key:
        task = live[selected_key]
        selected = target_context(db, uid, task['kind'], task['id'])
        selected['description'] = (selected['description'] or '')[:1200]
        selected['steps'] = selected['steps'][:10]
        rating = evaluated.get(selected_key)
        selected['recommendation'] = ({'level': rating['level'], 'reason': rating['reason']}
                                      if rating and not rating['stale'] and rating['analysis_status'] == 'analyzed'
                                      else {'level': None, 'reason': '当前尚未分析或评价已过期'})
    return {'tasks': summaries, 'omitted_count': max(0, len(live) - len(summaries)),
            'selected_task': selected, 'recommendation_status': view['status']}


def select_target(database, uid, cid, selected_key):
    with database.transaction() as db:
        lock_user(db, uid)
        chat = conversation(db, uid, cid)
        if selected_key and selected_key not in candidates(db, uid)[0]:
            raise AIError('invalid_target', '所选任务已不可用，请重新选择', 409)
        chat.selected_target_key = selected_key
        return {'selected_target_key': selected_key}


def send(database, settings, uid, data):
    excluded = {'request_id'} if data.selected_target_key else {'request_id', 'selected_target_key'}
    fingerprint = hashlib.sha256(data.model_dump_json(exclude=excluded).encode()).hexdigest()
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
        task_context = task_context_for_chat(db, uid, data.selected_target_key)
        chat.selected_target_key = data.selected_target_key
        pending = db.scalar(select(ChatTurn).where(ChatTurn.conversation_id == chat.id, ChatTurn.status == 'pending'))
        if pending:
            if pending.created_at > datetime.now(timezone.utc) - timedelta(minutes=2):
                raise AIError('busy', '上一条消息仍在处理中，请稍候查看历史', 409)
            pending.status, pending.error_code = 'failed', 'interrupted'
        current = db.get(StateCurrent, uid)
        snapshot = db.get(StateSnapshot, current.snapshot_id) if current else None
        state = {'pressure': snapshot.pressure, 'energy': snapshot.energy, 'difficulty': snapshot.difficulty[:1000]} if snapshot else None
        history = list(db.scalars(select(ChatTurn).where(ChatTurn.conversation_id == chat.id, ChatTurn.status == 'succeeded').order_by(ChatTurn.sequence.desc()).limit(6)))
        messages = context_messages(history, state, data.message, task_context)
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
