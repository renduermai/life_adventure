(() => {
    const $ = selector => document.querySelector(selector);
    const cards = new Map([...document.querySelectorAll('[data-spirit-feature]')]
        .map(card => [card.dataset.spiritFeature, card]));
    const reminders = $('#spirit-reminders');
    const summary = $('#spirit-summary');
    const refresh = $('#spirit-refresh');
    const open = $('#spirit-open-chat');
    const chat = $('#spirit-chat');
    const form = $('#spirit-question-form');
    const question = $('#spirit-question');
    const transcript = $('#spirit-transcript');
    const chatStatus = $('#spirit-chat-status');
    const clear = $('#spirit-clear');
    const history = [];
    let usageRead = 0;
    let hasInsight = false;
    let active = null;

    function paragraph(text) {
        const node = document.createElement('p');
        node.textContent = text;
        return node;
    }

    function featureLink(key) {
        const card = cards.get(key);
        if (!card) return null;
        const link = card.querySelector('.spirit-feature-link').cloneNode(true);
        link.className = 'button secondary';
        return link;
    }

    async function api(endpoint, data, signal) {
        const response = await fetch('/api/artifact-spirit/' + endpoint, {
            method: data ? 'POST' : 'GET',
            headers: data ? {'Content-Type': 'application/json'} : {},
            body: data ? JSON.stringify(data) : undefined,
            signal,
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.error || '请求失败，请稍后重试。');
        return payload;
    }

    function renderReminders(items) {
        reminders.replaceChildren();
        if (!items.length) reminders.append(paragraph('近期没有需要提示的功能区。'));
        for (const item of items) {
            const link = featureLink(item.feature);
            if (!link) continue;
            const block = document.createElement('div');
            block.className = 'spirit-reminder';
            block.append(paragraph(item.observation || '近 30 天打开 ' + item.recent + ' 次'));
            if (item.action) block.append(paragraph(item.action));
            block.append(link);
            reminders.append(block);
        }
    }

    async function readUsage() {
        const sequence = ++usageRead;
        try {
            const result = await api('usage');
            if (sequence !== usageRead) return;
            for (const item of result.items) {
                const count = cards.get(item.feature)?.querySelector('[data-spirit-count]');
                if (count) count.textContent = '近 ' + result.days + ' 天 ' + item.recent + ' 次 · 累计 ' + item.total + ' 次';
            }
            if (!hasInsight && !refresh.disabled) renderReminders(result.candidates);
        } catch (error) {
            if (sequence !== usageRead) return;
            $('#spirit-usage-status').textContent = error.message;
            if (!hasInsight && !refresh.disabled) reminders.replaceChildren(paragraph(error.message));
        }
    }

    refresh.addEventListener('click', async () => {
        refresh.disabled = true;
        summary.textContent = '正在根据近期次数和功能说明生成提醒…';
        try {
            const result = await api('remind', {request_id: crypto.randomUUID()});
            hasInsight = true;
            summary.textContent = result.summary;
            renderReminders(result.suggestions);
        } catch (error) {
            summary.textContent = error.message;
        } finally {
            refresh.disabled = false;
        }
    });

    open.addEventListener('click', () => {
        chat.hidden = !chat.hidden;
        open.setAttribute('aria-expanded', String(!chat.hidden));
        if (!chat.hidden) question.focus();
    });

    function resetChat() {
        active?.abort();
        active = null;
        history.length = 0;
        transcript.replaceChildren();
        question.value = '';
        chatStatus.textContent = '';
        form.querySelector('[type=submit]').disabled = false;
    }

    clear.addEventListener('click', () => {
        resetChat();
        question.focus();
    });
    window.addEventListener('pagehide', resetChat);

    form.addEventListener('submit', async event => {
        event.preventDefault();
        const text = question.value.trim();
        if (!text || active) return;
        const controller = new AbortController();
        active = controller;
        const send = form.querySelector('[type=submit]');
        send.disabled = true;
        chatStatus.textContent = '器灵正在查阅功能清单…';
        try {
            const result = await api('ask', {
                request_id: crypto.randomUUID(), question: text, history: history.slice(-4),
            }, controller.signal);
            if (active !== controller) return;
            history.push({question: text, answer: result.answer});
            if (history.length > 4) history.shift();
            const turn = document.createElement('article');
            turn.className = 'spirit-turn';
            const links = document.createElement('div');
            links.className = 'spirit-actions';
            for (const key of new Set(result.features)) {
                const link = featureLink(key);
                if (link) links.append(link);
            }
            turn.append(paragraph('你：' + text), paragraph('器灵：' + result.answer), links);
            transcript.append(turn);
            transcript.scrollTop = transcript.scrollHeight;
            if (question.value.trim() === text) question.value = '';
            chatStatus.textContent = '';
        } catch (error) {
            if (active === controller) chatStatus.textContent = error.message;
        } finally {
            if (active === controller) {
                active = null;
                send.disabled = false;
            }
        }
    });

    window.addEventListener('artifact-spirit-visit-recorded', readUsage);
    readUsage();
})();
