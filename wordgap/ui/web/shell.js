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
    escape() {
      const api = shell.api();
      if (api) api.escape();
    },
  };

  window.shell = shell;

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); shell.escape(); }
  });

  window.addEventListener("pywebviewready", () => {
    panels.forEach((p) => p.mount && p.mount());
    shell.updateStatus();
  });
})();
