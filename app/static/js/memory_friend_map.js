(() => {
    const endpoint = '/api/shining-memories/friends-map';
    const layers = [...document.querySelectorAll('[data-friend-layer]')];
    const plot = document.querySelector('#friend-quadrant-points');
    const status = document.querySelector('#friend-map-status');
    const selection = document.querySelector('#friend-map-selection');
    const reload = document.querySelector('#people-reload');
    let running = false;
    let readSequence = 0;

    async function request(path = '', payload) {
        const response = await fetch(endpoint + path, payload ? {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
        } : {});
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.error || '关系映射请求失败，请重试。');
        return body;
    }

    function dot(person, explanation, details) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'memory-friend-dot' + (person.stale ? ' stale' : '');
        button.title = person.name + (person.stale ? ' · 资料已变化，旧位置' : '');
        button.setAttribute('aria-label', button.title + ' · ' + explanation);
        button.addEventListener('click', () => {
            selection.hidden = false;
            selection.textContent = button.title + ' · ' + explanation + '。' + details;
            window.dispatchEvent(new CustomEvent('memory-friend-selected', {detail: person.id}));
        });
        return button;
    }

    function place(trust, resonance, occupied) {
        const right = trust >= 50;
        const upper = resonance >= 50;
        const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
        const x = (right ? 50 : 0) + 5 + 40 * ((trust - (right ? 50 : 0)) / 50);
        const y = (upper ? 0 : 50) + 23 + 22 * ((upper ? 100 - resonance : 50 - resonance) / 50);
        for (let attempt = 0; attempt < 60; attempt += 1) {
            const angle = attempt * 2.39996;
            const radius = Math.sqrt(attempt) * 2;
            const point = [
                clamp(x + Math.cos(angle) * radius, right ? 53 : 3, right ? 97 : 47),
                clamp(y + Math.sin(angle) * radius, upper ? 23 : 73, upper ? 47 : 97),
            ];
            if (!occupied.some(other => Math.hypot(point[0] - other[0], point[1] - other[1]) < 4)) return point;
        }
        return [x, y];
    }

    function render(items, updateStatus = true) {
        for (const layer of layers) layer.replaceChildren();
        plot.replaceChildren();
        selection.hidden = true;
        const occupied = [];
        let quadrantCount = 0;
        let layerCount = 0;
        for (const person of items) {
            const mapping = person.mapping;
            if (!mapping) continue;
            const highestLayer = mapping.layers.reduce(
                (highest, layer) => !highest || layer.layer > highest.layer ? layer : highest, null
            );
            if (highestLayer) {
                layerCount += 1;
                const target = layers[highestLayer.layer - 1];
                const title = target.parentElement.querySelector('strong').textContent;
                target.append(dot(person, title, highestLayer.reason));
            }
            if (!mapping.trust || !mapping.resonance) continue;
            quadrantCount += 1;
            const {trust, resonance} = mapping;
            const label = '可信度 ' + trust.score + '，共鸣度 ' + resonance.score;
            const point = dot(person, label, trust.reason + '；' + resonance.reason);
            const [x, y] = place(trust.score, resonance.score, occupied);
            occupied.push([x, y]);
            point.style.left = x + '%';
            point.style.top = y + '%';
            plot.append(point);
        }
        const pending = items.filter(item => item.status === 'pending').length;
        const insufficient = items.filter(item => item.mapping &&
            (!item.mapping.layers.length || !item.mapping.trust || !item.mapping.resonance)).length;
        const stale = items.filter(item => item.stale).length;
        if (updateStatus) status.textContent = !items.length
            ? '添加朋友并记录相处经历后，可点击「重新读取」生成散点。'
            : '五层图 ' + layerCount + ' 人 · 四象限 ' + quadrantCount + ' 人 · 待分析 ' +
                pending + ' 人 · 部分或全部依据不足 ' + insufficient + ' 人 · 资料更新 ' + stale + ' 人。';
    }

    async function read() {
        const sequence = ++readSequence;
        try {
            const {items} = await request();
            if (!running && sequence === readSequence) render(items);
        } catch (error) {
            if (!running && sequence === readSequence) status.textContent = error.message;
        }
    }

    window.addEventListener('memory-friends-changed', read);
    reload.addEventListener('click', async () => {
        if (running) return;
        running = true;
        reload.disabled = true;
        status.textContent = '正在读取朋友记录…';
        window.dispatchEvent(new Event('memory-friends-reload'));
        try {
            const {items} = await request();
            if (items.length && confirm(
                '允许将珍贵时刻、备注及最近 5 条相处事件的节选发送给灵石区所选模型？' +
                '\n单独保存的姓名和 Base 地字段不会发送。已有匹配结果会复用。'
            )) {
                let done = 0;
                let insufficient = 0;
                let cached = 0;
                const failures = [];
                for (const person of items) {
                    status.textContent = '正在读取关系映射 ' + (done + failures.length + 1) + '/' + items.length + '…';
                    try {
                        const result = await request('/' + person.id, {
                            request_id: crypto.randomUUID(),
                            expected_version: person.version,
                            consent_external: true,
                        });
                        Object.assign(person, result);
                        done += 1;
                        if (result.cached) cached += 1;
                        if (!result.mapping.layers.length || !result.mapping.trust || !result.mapping.resonance) insufficient += 1;
                    } catch (error) {
                        failures.push(person.name + '：' + error.message);
                    }
                }
                const refreshed = (await request()).items;
                render(refreshed, false);
                window.dispatchEvent(new CustomEvent('memory-friends-ranked', {detail: refreshed}));
                status.textContent = '读取完成 ' + done + '/' + items.length + '（复用 ' + cached +
                    '，部分或全部依据不足 ' + insufficient + '）。' +
                    (failures.length ? '失败 ' + failures.length + '，已有位置保留。' + failures.join('；') : '');
            } else {
                render(items);
            }
        } catch (error) {
            status.textContent = error.message;
        } finally {
            running = false;
            reload.disabled = false;
        }
    });
})();
