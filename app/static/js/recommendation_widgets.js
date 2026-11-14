(() => {
  const widgets = [...document.querySelectorAll('[data-recommendation-key]')];
  if (!widgets.length) return;
  const labels = {green:'绿色 · 当前推荐', white:'白色 · 一般', yellow:'黄色 · 不太推荐', red:'红色 · 很不推荐'};
  let loading = false;
  function paint(widget, item, batch) {
    const badge = widget.querySelector('[data-recommendation-badge]');
    const level = item && !item.stale && labels[item.level] ? item.level : 'unknown';
    badge.className = 'recommendation-badge recommendation-' + level;
    badge.textContent = item?.stale ? '已过期 · 待刷新' : labels[level] || '未评估';
    widget.querySelector('[data-recommendation-reason]').textContent = item?.stale ? '任务或状态已变化，请在启动状态中刷新。' : item?.reason || '请在启动状态中确认状态并分析任务。';
    widget.dataset.batchId = batch || '';
  }
  async function update() {
    if (loading || document.hidden) return;
    loading = true;
    try {
      const response = await fetch('/api/startup/recommendations');
      if (!response.ok) throw Error();
      const data = await response.json();
      const items = new Map(data.items.map(item => [item.key, item]));
      // Update the whole recommendation area from one response, including removals.
      for (const widget of widgets) paint(widget, items.get(widget.dataset.recommendationKey), data.batch_id);
    } catch {
      for (const widget of widgets) {
        paint(widget, null, null);
        widget.querySelector('[data-recommendation-reason]').textContent = '推荐暂不可用，请稍后刷新。';
      }
    } finally { loading = false; }
  }
  window.addEventListener('focus', update);
  document.addEventListener('visibilitychange', update);
  setInterval(update, 30000);
  update();
})();
