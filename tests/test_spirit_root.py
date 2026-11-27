import json
import os
import re
import socket
import threading
import time
from uuid import uuid4

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import load_settings, postgres_url
from app.modules.ai_gateway.models import AICallLog, AIConfig
from app.modules.ai_gateway.service import AIService
from app.modules.spirit_root.schemas import TextOutline
from app.modules.spirit_root.service import render_outline
from test_distractions_postgres import notes, task_engine

BASE = '/api/spirit-root'
H = {'Origin': 'http://testserver'}
ORIGINAL = '我把三次用户访谈的矛盾整理成分类模型，并用模型做了可交付的原型。'
SECOND = '试做求职工具时，我把访谈里的矛盾改写成可测试的产品规则。'
UNCERTAIN = '我把客户发来的问题整理成图谱，暂时不确定是不是同一种能力。'
FAIL = '这次我用另一个原型做了真实的交付测试。'


def test_outline_keeps_original_fragments_when_model_omits_some():
    segments = {'S1': '第一段', 'S2': '第二段原文', 'S3': '第三段原文'}
    outline = TextOutline.model_validate({'sections': [
        {'title': '主题二', 'segments': ['S3', 's3', 'S999']},
        {'title': '主题一', 'segments': ['S1']},
    ]})
    text = render_outline(segments, outline)
    assert text.startswith('1. 主题二')
    assert text.count('[S3]') == 1 and 'S999' not in text
    assert '其余原文\n  - [S2] 第二段原文' in text
    assert all(f'[{key}] {value}' in render_outline(segments, None) for key, value in segments.items())


@pytest.mark.integration
def test_spirit_root_evidence_and_browser(notes, monkeypatch):
    client, sessions, uid, other, app = notes
    calls = []
    invalid = True

    def fake_generate(self, uid, purpose, messages, request_id, **kwargs):
        payload = json.loads(messages[-1]['content'])
        if purpose == 'spirit_root_format':
            return {'content': {'sections': [{'title': '整理后的主题', 'segments': list(payload['segments'])}]}}
        assert purpose == 'spirit_root_probe'
        assert '1. 整理后的主题' in payload['organized_text']
        original = ''.join(re.findall(r'^  - \[S\d+\] (.+)$', payload['organized_text'], flags=re.M))
        calls.append(original)
        talent = dict(kind='talent', label='抽象建模', summary='从访谈抽象规则。',
                      strength='较强', reason='把矛盾整理成规则或分类。', quote=original,
                      match='new', existing_id=None, related_talents=['抽象建模'])
        if 'confirmed_talents' in payload:
            return {'content': {'cultivation': [{
                'talent': '抽象建模', 'advantage': '把混乱资料整理成可用规则。',
                'risk': '可能过度细分。', 'totem': False, 'quote': original,
            }], 'directions': []}}
        if original == ORIGINAL:
            signal = dict(kind='signal', label='把模型做成原型', summary='有把抽象模型转成原型的迹象。',
                          strength=None, reason='原文记载已制作原型。', quote=original,
                          match='new', existing_id=None, related_talents=['抽象建模'])
            return {'content': {'findings': [talent, talent, signal], 'cultivation': [{
                'talent': '抽象建模', 'advantage': '从访谈提取可交付的规则。',
                'risk': '可能在没有新数据时继续反复分类。', 'totem': True,
                'evidence_id': 'S1', 'quote': '这是模型改写的句子',
            }, {
                'talent': '抽象建模', 'advantage': '应该跳过这一项。',
                'risk': '也应该跳过。', 'totem': True, 'evidence_id': 'S999',
            }], 'directions': [{
                'kind': 'career', 'title': 'AI 应用工程师', 'horizon': '未来 1 年',
                'reason': '已有原型实践。', 'next_step': '做一项交付测试。', 'quote': original,
            }, {
                'kind': 'long_term', 'title': '决策产品', 'reason': '已有从访谈到模型的记录。',
                'next_step': '邀请一位使用者。', 'quote': original,
            }]}}
        if original == SECOND:
            talent.update(label='提炼抽象规则', match='same',
                          existing_id=next(row['id'] for row in payload['existing'] if row['kind'] == 'talent'))
            return {'content': {'findings': [talent], 'directions': [{
                'kind': 'career', 'title': 'AI 产品型工程师', 'horizon': '未来 1 年',
                'reason': '开始验证工程规则。', 'next_step': '收集测试反馈。', 'quote': original,
                'previous_key': next(item['key'] for item in payload['existing_directions'] if item['kind'] == 'career'),
            }]}}
        if original == UNCERTAIN:
            talent.update(label='问题图谱整理', match='uncertain',
                          existing_id=next(row['id'] for row in payload['existing'] if row['kind'] == 'talent'))
        if original == FAIL and invalid:
            talent['quote'] = '伪造的引用片段'
        return {'content': {'findings': [talent]}}

    monkeypatch.setattr(AIService, 'generate', fake_generate)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        origin = f'http://127.0.0.1:{sock.getsockname()[1]}'
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(.05)
            assert server.started
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel='msedge', headless=True)
                page = browser.new_page(viewport={'width': 1366, 'height': 910})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.context.add_cookies([{'name': 'camp_session', 'value': str(uid), 'url': origin}])
                page.goto(origin + '/spirit-root')
                expect(page.locator('.sidebar nav a').first).to_have_text('✺器灵')
                page.locator('#root-original').fill(ORIGINAL)
                page.get_by_role('button', name='AI 灵力探查').click()
                expect(page.locator('#root-talents')).to_contain_text('出现 1 次', timeout=20000)
                expect(page.locator('#root-status')).to_contain_text('另有 1 项依据不足')
                expect(page.locator('#root-signals')).to_contain_text('把模型做成原型')
                expect(page.locator('#root-totem-extra')).to_contain_text('抽象建模')
                expect(page.locator('#root-cultivation')).to_contain_text('可能的失控表现')
                expect(page.locator('#root-career')).to_contain_text('AI 应用工程师')
                expect(page.locator('#root-long-term')).to_contain_text('决策产品')
                page.locator('#root-totem-extra').get_by_role('button', name='抽象建模 · 查看依据').click()
                expect(page.locator('#root-dialog blockquote')).to_have_text(ORIGINAL)
                page.get_by_role('button', name='关闭', exact=True).click()
                page.get_by_role('button', name='抽象建模，较强，查看判断依据').click()
                expect(page.locator('#root-dialog blockquote')).to_have_text(ORIGINAL)
                page.get_by_role('button', name='查看完整原文').click()
                expect(page.locator('.root-original-view')).to_have_text(ORIGINAL)
                expect(page.get_by_role('button', name='删除原文')).to_be_visible()
                page.get_by_role('button', name='关闭', exact=True).click()
                page.locator('#root-signals').get_by_role('button', name='详情', exact=True).click()
                expect(page.locator('#root-dialog')).to_contain_text('关联天赋')
                page.get_by_role('button', name='关闭', exact=True).click()
                page.locator('#root-talents').get_by_role('button', name='编辑', exact=True).click()
                page.get_by_label('总结', exact=True).fill('编辑后的测试概括')
                page.get_by_label('天赋强度', exact=True).select_option('中等')
                page.get_by_role('button', name='保存', exact=True).click()
                expect(page.locator('#root-talents')).to_contain_text('编辑后的测试概括')
                expect(page.locator('#root-talents .root-pill')).to_have_text('中等')
                page.locator('#root-long-term').get_by_role('button', name='编辑', exact=True).click()
                page.get_by_label('验证一步', exact=True).fill('补测一位使用者')
                page.get_by_role('button', name='保存', exact=True).click()
                expect(page.locator('#root-long-term')).to_contain_text('补测一位使用者')
                page.reload()
                expect(page.locator('#root-talents')).to_contain_text('编辑后的测试概括')
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors
                browser.close()
        finally:
            server.should_exit = True
            thread.join(10)

    def probe(original):
        return client.post(BASE + '/probe', headers=H, json={'original': original})

    assert probe('  ' + ORIGINAL + '\n').json()['cached']
    assert calls == [ORIGINAL]
    assert probe(SECOND).status_code == 200
    data = client.get(BASE).json()
    talent = next(row for row in data['items'] if row['kind'] == 'talent')
    assert talent['label'] == '抽象建模' and talent['count'] == 2
    assert talent['linked_talents'] == []
    career = next(history for history in data['development']['directions'] if history[0]['kind'] == 'career')
    assert [item['title'] for item in career] == ['AI 产品型工程师', 'AI 应用工程师']
    from app.modules.spirit_root.models import ProbeSource
    with sessions.begin() as db:
        old = db.scalar(select(ProbeSource).where(ProbeSource.user_id == uid, ProbeSource.original == SECOND))
        old.development = None
        old_id = str(old.id)
    assert client.post(BASE + '/sources/' + old_id + '/enrich', headers=H, json={}).status_code == 200
    assert client.post(BASE + '/sources/' + old_id + '/enrich', headers=H, json={}).json()['cached']
    assert client.get(BASE).json()['items'][0]['count'] == 2
    assert len(client.get(BASE + '/entries/' + talent['id']).json()['items']) == 2
    assert probe(UNCERTAIN).status_code == 200
    pending = client.get(BASE).json()['review'][0]
    assert pending['suggested_label'] == '抽象建模'
    assert client.post(BASE + '/review/' + pending['id'], headers=H, json={'choice':'merge'}).status_code == 200
    invalid_result = probe(FAIL)
    assert invalid_result.status_code == 200 and invalid_result.json()['skipped'] == 1
    assert invalid_result.json()['state'] == 'failed'
    after_failure = client.get(BASE).json()
    assert after_failure['items'][0]['count'] == 3 and after_failure['review'] == []
    saved_id = after_failure['sources']['items'][0]['id']
    assert client.get(BASE + '/sources/' + saved_id).json()['original'] == FAIL
    assert after_failure['sources']['items'][0]['state'] == 'failed'
    invalid = False
    assert probe(FAIL).json()['id'] == saved_id
    assert client.get(BASE).json()['items'][0]['count'] == 4
    client.cookies.set('camp_session', str(other))
    assert client.get(BASE).json()['items'] == []
    assert client.get(BASE + '/sources/' + saved_id).status_code == 404
    assert client.get(BASE + '/entries/' + talent['id']).status_code == 404
    assert client.delete(BASE + '/entries/' + talent['id'], headers=H).status_code == 404
    assert client.patch(BASE + '/sources/' + saved_id, headers=H, json={'original':'越权修改'}).status_code == 404
    remove = BASE + '/sources/' + saved_id
    assert client.delete(remove, headers=H).status_code == 404
    client.cookies.set('camp_session', str(uid))
    assert client.delete(remove).status_code == 403
    assert client.delete(remove, headers=H).json()['deleted']
    assert client.get(remove).status_code == 404
    assert client.get(BASE).json()['items'][0]['count'] == 3

    sources = client.get(BASE + '/sources').json()
    first_id = next(row['id'] for row in sources['items'] if row['preview'] == ORIGINAL)
    snapshot = client.get(BASE).json()['development']
    node_id = snapshot['cultivation'][0][0]['talent_id']
    assert client.delete(BASE + '/development/totem/' + node_id, headers=H).status_code == 200
    assert not any(item['totem'] for history in client.get(BASE).json()['development']['cultivation'] for item in history)
    assert client.patch(BASE + '/sources/' + first_id, headers=H, json={'original':'编辑后的合成原文'}).status_code == 200
    assert client.get(BASE + '/sources/' + first_id).json()['original'] == '编辑后的合成原文'
    assert client.delete(BASE + '/sources/' + first_id, headers=H).status_code == 200
    remaining = client.get(BASE).json()
    assert [row['kind'] for row in remaining['items']] == ['talent']
    assert not any(history[0]['kind'] == 'long_term' for history in remaining['development']['directions'])
    assert not any(item['source_id'] == first_id for history in remaining['development']['cultivation'] for item in history)


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('LIFE_OS_LIVE') != '1', reason='真实模型未显式启用')
def test_real_spirit_root(notes, monkeypatch):
    client, sessions, uid, _, app = notes
    settings = load_settings()
    engine = create_engine(postgres_url(settings.database_url.get_secret_value()), hide_parameters=True)
    try:
        with Session(engine) as db:
            config = db.scalar(select(AIConfig).where(AIConfig.is_default.is_(True),
                AIConfig.enabled.is_(True), AIConfig.deleted_at.is_(None)).limit(1))
            assert config
            values = {key: getattr(config, key) for key in (
                'base_url', 'model_id', 'protocol', 'encrypted_key', 'key_version', 'key_mask',
            )}
    finally:
        engine.dispose()
    with sessions.begin() as db:
        db.add(AIConfig(user_id=uid, create_request_id=uuid4(), create_fingerprint='test',
                        name='灵根真实模型合成验收', is_default=True, **values))
    monkeypatch.undo()
    app.state.settings = settings
    original = ('【合成验收记录】  \n---\n>> 我把六次求职访谈整理成一套分类规则，写了工具把输入自动变成工作流。'
                '\n【附注】两位试用者反馈分类后更容易找到下一步。    我发现自己在两个独立项目中都用了这种从访谈到可运行工具的方法。'
                '\n>>> 另一个反复出现的行为：两个项目中，我在拿到试用反馈之前都连续三周加了用不上的功能。'
                '\n这周复盘发现第三个项目也重演了同样的过度开发，需要跟踪。')
    result = client.post(BASE + '/probe', headers=H, json={'original': original})
    assert result.status_code == 200, result.text
    items = client.get(BASE).json()['items']
    assert {item['kind'] for item in items} == {'talent','signal'}
    assert all(item['quote'] in original for item in items)
    development = client.get(BASE).json()['development']
    assert development['cultivation']
    assert all(item['quote'] in original for history in development['directions'] for item in history)
    assert client.post(BASE + '/probe', headers=H, json={'original': original}).json()['cached']

    with sessions() as db:
        logs = db.scalars(select(AICallLog).where(AICallLog.user_id == uid)
                          .order_by(AICallLog.started_at)).all()
        assert [(row.purpose, row.status) for row in logs] == [
            ('spirit_root_format', 'succeeded'), ('spirit_root_probe', 'succeeded'),
        ], [(row.purpose, row.error_code) for row in logs]
