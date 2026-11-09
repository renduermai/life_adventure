document.querySelectorAll('[data-quest-select]').forEach((quest) => {
  const milestone = quest.closest('form').querySelector('[data-milestone-select]');
  const update = (changed) => {
    for (const option of milestone.options) {
      if (option.dataset.quest) {
        const unavailable = option.dataset.quest !== quest.value;
        option.hidden = unavailable;
        option.disabled = unavailable;
        if (unavailable && option.selected) milestone.value = '';
      }
    }
    if (changed) milestone.value = '';
  };
  quest.addEventListener('change', () => update(true));
  update(false);
});
document.querySelectorAll('[data-go-back]').forEach((button) => {
  button.addEventListener('click', () => history.back());
});
// Do not send an empty UUID query parameter when filtering all quests.
document.querySelectorAll('form[method="get"]').forEach((form) => {
  form.addEventListener('submit', () => {
    for (const input of form.querySelectorAll('[name="quest"]')) {
      if (!input.value) input.disabled = true;
    }
  });
});
