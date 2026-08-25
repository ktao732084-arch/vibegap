/* Shell:面板挂载、状态栏、横幅、会话面板、词书菜单、焦点(spec §6)。 */
(function () {
  "use strict";

  const panels = [];
  const state = { sessionWords: 0, softClosing: false };
  const prefs = { auto_pronounce: true };
  const el = (id) => document.getElementById(id);

  const shell = {
    register(panel) { panels.push(panel); },
    state,
    prefs,
    api() { return window.pywebview && window.pywebview.api; },

    /* --- Python 侧回调 --- */
    onShow() {
      state.sessionWords = 0;
      state.softClosing = false;
      shell.closeOverlay();
      el("banner").classList.add("hidden");
      panels.forEach((p) => p.refresh && p.refresh());
      shell.updateStatus();
    },
    onReset() {
      state.softClosing = false;
      shell.closeOverlay();
      el("banner").classList.add("hidden");
      panels.forEach((p) => p.reset && p.reset());
    },
    onAgentFinished(info) {
      state.softClosing = true;
      const banner = el("banner");
      banner.textContent = info.waiting
        ? info.agent + " 等待确认 · 拼完当前词后收起"
        : info.agent + " 已完成 · 拼完当前词后收起";
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

    /* --- 状态栏 --- */
    updateStatus() {
      const api = shell.api();
      if (!api) return;
      api.get_progress().then((p) => {
        if (p.error) { el("status-text").textContent = "未导入词书"; return; }
        const mode = p.mode === "shuffled" ? "乱序" : "顺序";
        el("status-text").textContent =
          p.cursor + "/" + p.total + " · " + p.book_name + " · " + mode +
          " · 今日" + p.today + "/" + p.goal;
      }).catch(() => {});
    },
    updateAgents() {
      const api = shell.api();
      if (!api || !api.get_state) return;
      api.get_state().then((s) => {
        const box = el("status-agents");
        const busy = s.active_count > 0;
        box.innerHTML =
          '<span class="dot ' + (busy ? "busy" : "idle") + '"></span>' +
          "活跃" + s.active_count + " · 完成" + s.done_count;
        shell._sessions = s.sessions || [];
      }).catch(() => {});
    },

    /* --- 覆盖层:会话面板 / 词书菜单 --- */
    closeOverlay() { el("overlay").classList.add("hidden"); },
    isOverlayOpen() { return !el("overlay").classList.contains("hidden"); },
    showSessions() {
      const rows = (shell._sessions || []).map((s) => {
        const dot = '<span class="dot ' + (s.running ? "busy" : "idle") + '"></span>';
        const when = (s.last_event_at || "").slice(11, 16);
        const cwd = s.cwd || "";
        return '<div class="ov-row" data-cwd="' + esc(cwd) + '">' + dot +
          '<span class="ov-main">' + esc(s.agent) +
          ' <span class="ov-sub">' + esc(s.session_id.slice(0, 8)) + " · " + when +
          (cwd ? " · " + esc(shortPath(cwd)) : "") + "</span></span>" +
          '<span class="ov-sub">' + (s.running ? "运行中" : "已完成") + "</span></div>";
      });
      openOverlay("<h4>会话(点击打开项目目录)</h4>" +
        (rows.length ? rows.join("") : '<div class="ov-sub">还没有会话</div>'));
      el("overlay").querySelectorAll(".ov-row").forEach((row) => {
        row.addEventListener("click", () => {
          const cwd = row.getAttribute("data-cwd");
          const api = shell.api();
          if (cwd && api) api.open_path(cwd);
        });
      });
    },
    showBooks() {
      const api = shell.api();
      if (!api) return;
      api.list_books().then((books) => {
        const rows = books.map((b) =>
          '<div class="ov-row" data-book="' + b.id + '">' +
          '<span class="ov-main' + (b.current ? " ov-cur" : "") + '">' +
          esc(b.name) + '</span><span class="ov-sub">' + b.count + " 词" +
          (b.current ? " · 当前" : "") + "</span></div>");
        openOverlay("<h4>切换词书</h4>" + rows.join(""));
        el("overlay").querySelectorAll(".ov-row").forEach((row) => {
          row.addEventListener("click", () => {
            api.set_book(parseInt(row.getAttribute("data-book"), 10)).then(() => {
              shell.closeOverlay();
              shell.updateStatus();
              panels.forEach((p) => p.refresh && p.refresh());
            });
          });
        });
      });
    },

    startReview() {
      shell.closeOverlay();
      panels.forEach((p) => p.startReview && p.startReview());
    },
    escape() {
      const api = shell.api();
      if (api) api.escape().catch(() => {});
    },
  };

  function openOverlay(html) {
    const ov = el("overlay");
    ov.innerHTML = html;
    ov.classList.remove("hidden");
  }
  function esc(s) {
    const div = document.createElement("div");
    div.textContent = s == null ? "" : String(s);
    return div.innerHTML;
  }
  function shortPath(p) {
    const parts = String(p).split(/[\\/]/).filter(Boolean);
    return parts.length > 2 ? "…/" + parts.slice(-2).join("/") : p;
  }

  window.shell = shell;

  // Esc 分层:面板内部模式(复习/浏览)→ 覆盖层 → 隐藏窗口。捕获阶段监听。
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    e.preventDefault();
    if (shell.isOverlayOpen()) { shell.closeOverlay(); return; }
    const consumed = panels.some((p) => p.handleEscape && p.handleEscape());
    if (!consumed) shell.escape();
  }, true);

  // 点击窗口任意处 = 用户要输入:向系统要键盘焦点(窗口默认不抢焦点)
  document.addEventListener("mousedown", () => {
    const api = shell.api();
    if (api && api.request_focus) api.request_focus();
  }, true);

  window.addEventListener("pywebviewready", () => {
    el("btn-close").addEventListener("click", () => shell.escape());
    el("status-agents").addEventListener("click", () => {
      shell.isOverlayOpen() ? shell.closeOverlay() : shell.showSessions();
    });
    el("status-text").addEventListener("click", () => {
      shell.isOverlayOpen() ? shell.closeOverlay() : shell.showBooks();
    });
    el("btn-review").addEventListener("click", () => shell.startReview());
    const soundBtn = el("btn-sound");
    const renderSound = () => {
      soundBtn.textContent = prefs.auto_pronounce ? "🔊" : "🔇";
      soundBtn.title = prefs.auto_pronounce ? "自动发音:开" : "自动发音:关(点音标仍可发音)";
    };
    soundBtn.addEventListener("click", () => {
      prefs.auto_pronounce = !prefs.auto_pronounce;
      renderSound();
      const api = shell.api();
      if (api) api.set_pref("auto_pronounce", prefs.auto_pronounce);
    });
    const apiNow = shell.api();
    if (apiNow && apiNow.get_prefs) {
      apiNow.get_prefs().then((p) => {
        prefs.auto_pronounce = !!p.auto_pronounce;
        renderSound();
      }).catch(renderSound);
    } else { renderSound(); }
    panels.forEach((p) => p.mount && p.mount());
    shell.updateStatus();
    shell.updateAgents();
    setInterval(shell.updateAgents, 3000);
  });
})();
