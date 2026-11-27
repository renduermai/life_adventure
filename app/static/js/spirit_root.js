(() => {
    const $ = selector => document.querySelector(selector);
    const form = $('#root-form');
    const input = $('#root-original');
    const submit = form.querySelector('[type=submit]');
    const status = $('#root-status');
    const analysisState = $('#root-analysis-state');
    const analysisLabels = {running: '分析中…', failed: '分析失败', succeeded: '分析成功'};
    const dialog = $('#root-dialog');
    const dialogTitle = $('#root-dialog-title');
    const dialogContent = $('#root-dialog-content');
    const date = new Intl.DateTimeFormat(document.documentElement.lang, {dateStyle: 'medium', timeStyle: 'short'});
    let entries = new Map();
    let dialogRequest = 0;
    let readRequest = 0;

    function showAnalysisState(state) {
        analysisState.dataset.state = state;
        analysisState.textContent = analysisLabels[state] || '';
    }

    async function api(path = '', payload, method = payload ? 'POST' : 'GET') {
        const response = await fetch('/api/spirit-root' + path, {
            method,
            headers: payload ? {'Content-Type': 'application/json'} : {},
            body: payload ? JSON.stringify(payload) : undefined,
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.error || '操作失败，请稍后重试。');
        return result;
    }

    function node(tag, text, className) {
        const item = document.createElement(tag);
        item.textContent = text ?? '';
        if (className) item.className = className;
        return item;
    }

    function button(text, action, className = 'button secondary') {
        const item = node('button', text, className);
        item.type = 'button';
        item.addEventListener('click', action);
        return item;
    }

    function openDialog(title) {
        const request = ++dialogRequest;
        dialogTitle.textContent = title;
        dialogContent.replaceChildren(node('p', '正在读取…', 'muted'));
        if (!dialog.open) dialog.showModal();
        return request;
    }

    function editRecord(title, path, fields, warning = '') {
        const request = openDialog(title);
        const editor = node('form', '', 'form-stack');
        const controls = new Map();
        for (const [key, label, value, max, multiline, options] of fields) {
            const wrapper = node('label', label);
            const control = node(options ? 'select' : multiline ? 'textarea' : 'input');
            control.setAttribute('aria-label', label);
            if (options) {
                for (const option of options) control.append(node('option', option));
            } else control.maxLength = max;
            control.value = value ?? '';
            control.required = key !== 'horizon';
            if (multiline) control.rows = key === 'original' ? 7 : 3;
            controls.set(key, control);
            wrapper.append(control);
            editor.append(wrapper);
        }
        if (warning) editor.append(node('p', warning, 'muted'));
        const save = node('button', '保存', 'button primary');
        save.type = 'submit';
        const feedback = node('p', '', 'muted');
        feedback.setAttribute('role', 'status');
        editor.append(save, feedback);
        editor.addEventListener('submit', async event => {
            event.preventDefault();
            save.disabled = true;
            try {
                const data = Object.fromEntries([...controls].map(([key, element]) => [key, element.value]));
                await api(path, data, 'PATCH');
                if (request === dialogRequest) {
                    if (controls.has('original') && input.value === fields[0][2]) input.value = '';
                    dialog.close();
                    status.textContent = controls.has('original') ? '原文已更新，请重新探查。' : '修改已保存。';
                }
                await read();
            } catch (error) {
                feedback.textContent = error.message;
                save.disabled = false;
            }
        });
        dialogContent.replaceChildren(editor);
        controls.values().next().value.focus();
    }

    function deleteRecord(path, warning, sourceText) {
        if (!confirm(warning)) return;
        const request = dialogRequest;
        api(path, undefined, 'DELETE').then(async () => {
            if (request === dialogRequest && dialog.open) dialog.close();
            if (sourceText !== undefined && input.value === sourceText) input.value = '';
            status.textContent = '记录已删除。';
            await read();
        }).catch(error => {
            if (request === dialogRequest && dialog.open) dialogContent.append(node('p', error.message));
            else status.textContent = error.message;
        });
    }

    function recordActions(edit, remove, label = '') {
        const actions = node('div', '', 'root-actions root-record-actions');
        actions.append(button('编辑' + label, edit, 'root-text-action'), button('删除' + label, remove, 'root-text-action root-delete'));
        return actions;
    }

    function recordHeading(content, actions) {
        const heading = node('div', '', 'root-record-heading');
        heading.append(content, actions);
        return heading;
    }

    function strengthField(item) {
        if (item.kind !== 'talent') return [];
        return [['strength', '天赋强度', item.strength, 0, false, ['强', '较强', '已有外部信号', '中等', '正在形成', '待验证']]];
    }

    function observationActions(item) {
        const path = '/observations/' + (item.observation_id || item.id);
        return recordActions(
            () => editRecord('编辑记录', path, [
                ['label', '名称', item.label, 80], ['summary', '总结', item.summary, 200, true],
                ['reason', '判断依据说明', item.reason, 220, true], ...strengthField(item),
            ], '原文片段可在原文详情页修改，修改后需重新探查。'),
            () => deleteRecord(path, '确定删除这条分析记录？对应的出现次数会重新计算。'),
        );
    }

    function sourceEditor(item) {
        editRecord('编辑原文', '/sources/' + item.id, [
            ['original', '原文', item.original, 10000, true],
        ], '保存后，这段原文原有的分析记录会移除。你可以用改后的原文重新探查。');
    }

    function developmentActions(group, item, allVersions = false) {
        const isDirection = group === 'directions';
        const path = '/development/' + group + '/' + (isDirection ? item.key : item.talent_id);
        const version = path + '?source_id=' + item.source_id;
        const fields = isDirection ? [
            ['title', '名称', item.title, 80], ['horizon', '时间阶段', item.horizon, 60],
            ['reason', '判断依据说明', item.reason, 200, true],
            ['next_step', '验证一步', item.next_step, 160, true],
        ] : [
            ['advantage', '潜在优势', item.advantage, 160, true],
            ['risk', '可能的失控表现', item.risk, 160, true],
        ];
        const warning = group === 'totem' ? '确定将这个节点从图腾移除？修炼记录仍会保留。'
            : allVersions ? '确定删除此条目及其所有分析版本？原文会保留。' : '确定删除这条历史记录？原文会保留。';
        return recordActions(() => editRecord('编辑分析', version, fields),
            () => deleteRecord(allVersions ? path : version, warning));
    }

    function evidence(item) {
        const block = node('article', '', 'root-item');
        const heading = date.format(new Date(item.created_at)) + (item.strength ? ' · ' + item.strength : '');
        const actions = observationActions(item);
        actions.prepend(button('查看完整原文', () => showSource(item.source_id), 'root-text-action'));
        block.append(recordHeading(node('strong', heading), actions), node('p', item.reason),
            node('blockquote', item.quote, 'root-quote'));
        if (item.linked_talents.length) {
            const links = node('div', '', 'root-actions');
            links.append(node('span', '关联天赋', 'muted'));
            for (const id of item.linked_talents) {
                const talent = entries.get(id);
                if (talent) links.append(button(talent.label, () => showHistory(talent)));
            }
            block.append(links);
        }
        return block;
    }

    async function showSource(id, editing = false) {
        const request = openDialog('提交原文');
        try {
            const item = await api('/sources/' + id);
            if (!dialog.open || request !== dialogRequest) return;
            dialogContent.replaceChildren(node('p', item.original, 'root-original-view'));
            if (editing) {
                sourceEditor(item);
                return;
            }
            dialogContent.append(recordActions(() => sourceEditor(item),
                () => deleteRecord('/sources/' + id,
                    '删除后，这段原文和它提供的证据会移除，各项出现次数将重新计算。确定删除？',
                    item.original), '原文'));
            if (item.needs_development) {
                const message = node('p', '', 'muted');
                message.setAttribute('role', 'status');
                const enrich = button('补充图腾与发展分析', async () => {
                    enrich.disabled = true;
                    message.textContent = '正在将原文交给灵石区模型补充分析…';
                    try {
                        const result = await api('/sources/' + id + '/enrich', {});
                        await read();
                        if (request === dialogRequest) {
                            message.textContent = result.skipped
                                ? '已保存有依据的条目，' + result.skipped + ' 项暂未纳入。'
                                : '补充完成，可以关闭查看新版结果。';
                            if (result.needs_development) enrich.disabled = false;
                            else enrich.remove();
                        }
                    } catch (error) {
                        if (request === dialogRequest) message.textContent = error.message;
                        enrich.disabled = false;
                    }
                });
                dialogContent.append(node('p', '补充分析会把这段原文发送给灵石区模型。', 'muted'), enrich, message);
            }
            if (item.state !== 'succeeded') {
                dialogContent.append(button('使用这段原文重试', () => {
                    input.value = item.original;
                    dialog.close();
                    input.focus();
                }));
            }
        } catch (error) {
            if (request === dialogRequest) dialogContent.replaceChildren(node('p', error.message));
        }
    }

    function showHistory(item) {
        const request = openDialog(item.label + ' · 记录与证据');
        async function next(offset) {
            try {
                const result = await api('/entries/' + item.id + '?offset=' + offset);
                if (!dialog.open || request !== dialogRequest) return;
                if (offset === 0) dialogContent.replaceChildren();
                dialogContent.append(...result.items.map(evidence));
                if (result.next_offset !== null) {
                    const more = button('加载更早的记录', () => {
                        more.remove();
                        next(result.next_offset);
                    });
                    dialogContent.append(more);
                }
            } catch (error) {
                if (request === dialogRequest) dialogContent.append(node('p', error.message));
            }
        }
        next(0);
    }

    function renderList(target, items, emptyText) {
        target.replaceChildren();
        if (!items.length) target.append(node('p', emptyText, 'muted'));
        for (const item of items) {
            const article = node('article', '', 'root-item');
            const line = node('div', '', 'root-label-line');
            const title = node('h3');
            title.append(button(item.label, () => showHistory(item), 'root-label'));
            line.append(title, node('span', '出现 ' + item.count + ' 次', 'muted'));
            if (item.strength) {
                const tag = button(item.strength, () => {
                    openDialog(item.label + ' · ' + item.strength);
                    dialogContent.replaceChildren(evidence(item));
                }, 'root-pill');
                tag.dataset.strength = item.strength;
                tag.setAttribute('aria-label', item.label + '，' + item.strength + '，查看判断依据');
                line.append(tag);
            }
            const path = '/entries/' + item.id;
            const actions = recordActions(() => editRecord('编辑条目', path, [
                ['label', '名称', item.label, 80], ['summary', '总结', item.summary, 200, true], ...strengthField(item),
            ]), () => deleteRecord(path, '确定删除此条目及其分析历史？提交的原文仍会保留。'));
            if (item.kind === 'signal') actions.prepend(button('详情', () => showHistory(item), 'root-text-action'));
            const heading = node('div', '', 'root-record-heading');
            heading.append(line, actions);
            article.append(heading, node('p', item.summary));
            target.append(article);
        }
    }

    function renderReview(items) {
        const panel = $('#root-review');
        const target = $('#root-review-items');
        panel.hidden = !items.length;
        target.replaceChildren();
        for (const item of items) {
            const block = node('article', '', 'root-item');
            const actions = node('div', '', 'root-actions');
            const feedback = node('p', '', 'muted');
            feedback.setAttribute('role', 'status');
            async function resolve(choice) {
                for (const control of actions.children) control.disabled = true;
                try {
                    await api('/review/' + item.id, {choice});
                    await read();
                } catch (error) {
                    feedback.textContent = error.message;
                    for (const control of actions.children) control.disabled = false;
                }
            }
            if (item.suggested_label) actions.append(button('合并到已有条目', () => resolve('merge')));
            actions.append(button('保留为独立条目', () => resolve('separate')));
            const suggestion = item.suggested_label ? '可能与「' + item.suggested_label + '」相近。' : '原建议的关联条目已移除。';
            block.append(recordHeading(node('h3', item.label), observationActions(item)), node('p', suggestion),
                node('p', item.summary), node('blockquote', item.quote, 'root-quote'), actions, feedback);
            target.append(block);
        }
    }

    function renderSources({items, next_offset: offset}, append = false) {
        const target = $('#root-sources');
        if (!append) target.replaceChildren();
        if (!append && !items.length) target.append(node('p', '还没有探查记录。', 'muted'));
        const states = {running: '探查中', failed: '未完成，可重试', succeeded: '已探查'};
        for (const item of items) {
            const row = node('article', '', 'root-item');
            const actions = recordActions(() => showSource(item.id, true), () => deleteRecord('/sources/' + item.id,
                '确定删除这段原文及其关联证据？出现次数会重新计算。'));
            actions.prepend(button('查看原文', () => showSource(item.id), 'root-text-action'));
            row.append(recordHeading(node('strong', date.format(new Date(item.created_at)) + ' · ' + states[item.state]), actions),
                node('p', item.preview));
            target.append(row);
        }
        if (offset !== null) {
            const more = button('加载更早的原文', async () => {
                more.disabled = true;
                const pending = readRequest;
                try {
                    const result = await api('/sources?offset=' + offset);
                    if (pending !== readRequest) return;
                    more.remove();
                    renderSources(result, true);
                } catch (error) {
                    more.after(node('p', error.message, 'muted'));
                    more.disabled = false;
                }
            });
            target.append(more);
        }
    }

    function developmentHistory(title, history, kind) {
        openDialog(title + ' · 变更与原文证据');
        dialogContent.replaceChildren(...history.map(record => {
            const block = node('article', '', 'root-item');
            const actions = developmentActions(kind === 'cultivation' ? 'cultivation' : 'directions', record);
            actions.prepend(button('查看完整原文', () => showSource(record.source_id), 'root-text-action'));
            block.append(recordHeading(node('strong', date.format(new Date(record.created_at))), actions));
            if (kind === 'cultivation') {
                block.append(node('p', '潜在优势 · ' + record.advantage), node('p', '可能的失控表现 · ' + record.risk));
            } else {
                block.append(node('p', [record.horizon, record.title].filter(Boolean).join(' · ')),
                    node('p', record.reason), node('p', '验证一步 · ' + record.next_step));
            }
            block.append(node('blockquote', record.quote, 'root-quote'));
            return block;
        }));
    }

    function renderDevelopment(development) {
        const extra = $('#root-totem-extra');
        extra.replaceChildren();
        for (const control of document.querySelectorAll('[data-base-totem] button, [data-base-totem] .root-record-actions')) control.remove();

        const cultivation = $('#root-cultivation');
        cultivation.replaceChildren();
        if (!development.cultivation.length) cultivation.append(node('p', '暂无有原文依据的修炼记录。', 'muted'));
        for (const history of development.cultivation) {
            const latest = history[0];
            const talent = entries.get(latest.talent_id);
            if (!talent) continue;
            const show = () => developmentHistory(talent.label, history, 'cultivation');
            const block = node('article', '', 'root-item');
            const compare = node('div', '', 'root-compare');
            for (const [title, text, color] of [
                ['潜在优势', latest.advantage, 'root-advantage'],
                ['可能的失控表现', latest.risk, 'root-risk'],
            ]) {
                const part = node('div', '', color);
                part.append(node('strong', title), node('p', text));
                compare.append(part);
            }
            const heading = node('div', '', 'root-record-heading');
            const controls = developmentActions('cultivation', latest, true);
            controls.prepend(button('查看依据', show, 'root-text-action'));
            heading.append(node('h3', talent.label), controls);
            block.append(heading, compare);
            cultivation.append(block);

            const support = history.filter(item => item.totem);
            if (!support.length) continue;
            const showTotem = () => developmentHistory(talent.label, support, 'cultivation');
            const seed = [...document.querySelectorAll('[data-base-totem]')]
                .find(element => element.dataset.baseTotem === talent.label);
            const totemControls = developmentActions('totem', support[0], true);
            if (seed) seed.append(button('查看依据', showTotem, 'root-label'), totemControls);
            else {
                const added = node('div', '', 'root-totem-node root-totem-added');
                added.append(button(talent.label + ' · 查看依据', showTotem, 'root-label'), totemControls);
                extra.append(added);
            }
        }
        extra.hidden = !extra.childElementCount;

        for (const [kind, selector] of [['career', '#root-career'], ['long_term', '#root-long-term']]) {
            const target = $(selector);
            target.replaceChildren();
            const histories = development.directions.filter(history => history[0].kind === kind);
            if (!histories.length) target.append(node('p', '暂无有原文依据的条目。', 'muted'));
            if (kind === 'career') {
                const stage = entry => Number(entry[0].horizon.match(/\d+/)?.[0] ?? 1000);
                histories.sort((a, b) => stage(a) - stage(b));
            }
            for (const history of histories) {
                const item = history[0];
                const block = node('article', '', 'root-item');
                if (item.horizon) block.append(node('p', item.horizon, 'muted'));
                const heading = node('div', '', 'root-record-heading');
                const controls = developmentActions('directions', item, true);
                controls.prepend(button('查看依据与历史', () => developmentHistory(item.title, history, kind), 'root-text-action'));
                heading.append(node('h4', item.title), controls);
                block.append(heading, node('p', item.reason), node('p', '验证一步 · ' + item.next_step));
                target.append(block);
            }
        }
    }

    async function read() {
        const request = ++readRequest;
        try {
            const result = await api();
            if (request !== readRequest) return;
            entries = new Map(result.items.map(item => [item.id, item]));
            renderList($('#root-talents'), result.items.filter(item => item.kind === 'talent'), '还没有天赋记录。');
            renderList($('#root-signals'), result.items.filter(item => item.kind === 'signal'), '还没有捕捉到信号。');
            renderReview(result.review);
            renderSources(result.sources);
            if (!analysisState.dataset.state && result.sources.items.length) {
                showAnalysisState(result.sources.items[0].state);
            }
            renderDevelopment(result.development);
        } catch (error) {
            if (request !== readRequest) return;
            for (const target of [$('#root-talents'), $('#root-signals')]) {
                target.replaceChildren(node('p', error.message, 'muted'));
            }
        }
    }

    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (!input.value.trim() || submit.disabled) return;
        const original = input.value;
        submit.disabled = true;
        showAnalysisState('running');
        status.textContent = '正在分层整理原文，再逐区分析…';
        try {
            const result = await api('/probe', {original});
            showAnalysisState(result.state === 'failed' ? 'failed' : 'succeeded');
            if (result.cached) {
                status.textContent = '这段原文已探查过，已读取已有结果。';
            } else if (result.state === 'failed') {
                status.textContent = '原文已保存。此次没有定位到可用依据，可以重新探查。';
            } else if (result.findings || result.developed) {
                status.textContent = '已整理并分区保存 ' + (result.findings + result.developed)
                    + ' 项有依据的结果。' + (result.skipped ? '另有 ' + result.skipped + ' 项依据不足，暂未纳入。' : '');
            } else {
                status.textContent = '原文已保存，这次没有提取到有足够依据的新发现。';
            }
            if (result.state !== 'failed' && input.value === original) input.value = '';
        } catch (error) {
            showAnalysisState('failed');
            status.textContent = error.message;
        } finally {
            await read();
            submit.disabled = false;
        }
    });

    read();
})();
