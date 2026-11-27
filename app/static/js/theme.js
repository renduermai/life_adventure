(() => {
  let theme = "dark";
  try { theme = localStorage.getItem("adventure-camp-theme") || theme; } catch (_) {}
  document.documentElement.dataset.theme = theme === "light" ? "light" : "dark";
})();
