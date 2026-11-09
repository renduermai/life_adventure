(() => {
  const root = document.documentElement;
  const toggle = document.getElementById("theme-toggle");
  function updateTheme(theme) {
    root.dataset.theme = theme;
    try { localStorage.setItem("adventure-camp-theme", theme); } catch (_) {}
    toggle.setAttribute("aria-label", theme === "dark" ? "切换到浅色主题" : "切换到深色主题");
    document.querySelectorAll("[data-set-theme]").forEach(button => {
      button.setAttribute("aria-pressed", String(button.dataset.setTheme === theme));
    });
  }
  updateTheme(root.dataset.theme);
  toggle.addEventListener("click", () => updateTheme(root.dataset.theme === "dark" ? "light" : "dark"));
  document.querySelectorAll("[data-set-theme]").forEach(button => button.addEventListener("click", () => updateTheme(button.dataset.setTheme)));
  const menu = document.getElementById("menu-button");
  const scrim = document.getElementById("scrim");
  function setMenu(open) {
    document.body.classList.toggle("menu-open", open);
    menu.setAttribute("aria-expanded", String(open));
    menu.setAttribute("aria-label", open ? "关闭导航" : "打开导航");
    scrim.hidden = !open;
  }
  menu.addEventListener("click", () => setMenu(menu.getAttribute("aria-expanded") !== "true"));
  scrim.addEventListener("click", () => setMenu(false));
  document.addEventListener("keydown", event => { if (event.key === "Escape") { setMenu(false); menu.focus(); } });
  const check = document.getElementById("check-database");
  if (check) check.addEventListener("click", async () => {
    const output = document.getElementById("database-result");
    check.disabled = true;
    output.textContent = "正在检查连接…";
    try {
      const response = await fetch("/health/ready", { signal: AbortSignal.timeout(12000) });
      const result = await response.json();
      output.textContent = result.message || "检查未完成，请稍后重试。";
    } catch (_) { output.textContent = "检查未完成，请确认服务运行后重试。"; }
    finally { check.disabled = false; }
  });
})();
