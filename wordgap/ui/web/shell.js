/* Shell:面板挂载、状态栏、横幅、生命周期(spec §6 面板契约)。 */
(function () {
  "use strict";

  const panels = [];
  const state = { sessionWords: 0, softClosing: false };

  const el = (id) => document.getElementById(id);

  const shell = {
    /* --- 面板注册(word_card / news_ticker 调用) --- */
    register(panel) { panels.push(panel); },

    state,

    api() { return window.pywebview && window.pywebview.api; },

    /* --- Python 侧回调(WindowNotifier 经 evaluate_js 调用) --- */
    onShow() {
      state.sessionWords = 0;
      state.softClosing = false;
      el("banner").classList.add("hidden");
      panels.forEach((p) => p.refresh && p.refresh());
      shell.updateStatus();
    },
    onReset() {
      state.softClosing = false;
      el("banner").classList.add("hidden");
      panels.forEach((p) => p.reset && p.reset());
    },
    onAgentFinished(info) {
      state.softClosing = true;
      const banner = el("banner");
      banner.textContent = info.waiting
        ? "⏸ " + info.agent + " 在等你确认 — 拼完这个词就过去"
        : "✅ " + info.agent + " 跑完了 — 拼完这个词收工";
      banner.classList.toggle("waiting", !!info.waiting);
      banner.classList.remove("hidden");
    },
    onClearBanner() {
      state.softClosing = false;
      el("banner").classList.add("hidden");
    },
    onSummary() {
      panels.forEach((p) => p.showSummary && p.showSummary(state.sessionWords));
    },

    /* --- 工具 --- */
    updateStatus() {
      const api = shell.api();
      if (!api) return;
      api.get_progress().then((p) => {
        if (p.error) { el("status-text").textContent = "未导入词书"; return; }
        const mode = p.mode === "shuffled" ? "乱序" : "顺序";
        el("status-text").textContent =
          p.cursor + "/" + p.total + " · " + p.book_name + " · " + mode;
      });
    },
    updateAgents() {
      const api = shell.api();
      if (!api || !api.get_state) return;
      api.get_state().then((s) => {
        const box = el("status-agents");
        if (!s.running_agents || !s.running_agents.length) {
          box.innerHTML = '<span class="dot idle"></span>空闲';
        } else {
          box.innerHTML =
            '<span class="dot busy"></span>' + s.running_agents.join(" · ") + " 运行中";
        }
      }).catch(() => {});
    },
    escape() {
      const api = shell.api();
      if (api) api.escape().catch(() => {});
    },
  };

  window.shell = shell;

  // 捕获阶段 + keyup 双监听:任何组件都无法吞掉 Esc
  const onEsc = (e) => {
    if (e.key === "Escape") { e.preventDefault(); shell.escape(); }
  };
  document.addEventListener("keydown", onEsc, true);
  document.addEventListener("keyup", onEsc, true);

  window.addEventListener("pywebviewready", () => {
    el("btn-close").addEventListener("click", () => shell.escape());
    panels.forEach((p) => p.mount && p.mount());
    shell.updateStatus();
    shell.updateAgents();
    setInterval(shell.updateAgents, 3000);
  });
})();
