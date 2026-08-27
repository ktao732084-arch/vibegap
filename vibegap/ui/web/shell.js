/* Shell:面板挂载、状态栏、横幅、会话面板、词书菜单、焦点(spec §6)。 */
(function () {
  "use strict";

  const panels = [];
  const state = { sessionWords: 0, softClosing: false };
  const prefs = { auto_pronounce: true, theme: "auto" };
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
      const base = info.waiting ? info.agent + " 等待确认" : info.agent + " 已完成";
      banner.textContent = base;
      banner.classList.toggle("waiting", !!info.waiting);
      banner.classList.remove("hidden");
      const api = shell.api();
      if (api && api.get_state) {
        // 文案如实反映:还有别的任务在跑就不承诺"收起"
        api.get_state().then((s) => {
          if (!state.softClosing) return;
          banner.textContent = base +
            (s.active_count > 0 ? " · 其他任务仍在运行,继续背" : " · 拼完当前词后收起");
        }).catch(() => {});
      }
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
        el("status-text").textContent =
          p.cursor + "/" + p.total + " " + p.book_name + " · 今" + p.today + "/" + p.goal;
      }).catch(() => {});
    },
    updateAgents() {
      const api = shell.api();
      if (!api || !api.get_state) return;
      api.get_state().then((s) => {
        const box = el("status-agents");
        shell._sessions = s.sessions || [];
        const byAgent = {};
        shell._sessions.forEach((sess) => {
          const key = sess.agent;
          if (!byAgent[key]) byAgent[key] = { active: 0, done: 0 };
          byAgent[key][sess.running ? "active" : "done"] += 1;
        });
        const names = Object.keys(byAgent);
        if (!names.length) {
          box.innerHTML = '<span class="dot idle"></span>空闲';
          return;
        }
        const fmt = (a) => {
          const parts = [];
          if (a.active) parts.push("活" + a.active);
          if (a.done) parts.push("完" + a.done);
          return parts.join(" ");
        };
        if (names.length === 1) {
          const a = byAgent[names[0]];
          box.innerHTML = '<span class="dot ' + (a.active ? "busy" : "idle") + '"></span>' +
            shortAgent(names[0]) + " " + fmt(a);
          return;
        }
        // 多 agent 收拢为汇总,防止挤占状态栏;明细在会话面板(点击查看)
        const total = { active: 0, done: 0 };
        names.forEach((name) => {
          total.active += byAgent[name].active;
          total.done += byAgent[name].done;
        });
        box.innerHTML = '<span class="dot ' + (total.active ? "busy" : "idle") + '"></span>' +
          fmt(total);
        box.title = names.map((n) => shortAgent(n) + " " + fmt(byAgent[n])).join(" | ");
      }).catch(() => {});
    },

    /* --- 覆盖层:会话面板 / 词书菜单 / 设置。同键关闭,异键直接切换 --- */
    _overlayKind: null,
    closeOverlay() {
      el("overlay").classList.add("hidden");
      shell._overlayKind = null;
    },
    isOverlayOpen() { return !el("overlay").classList.contains("hidden"); },
    toggleOverlay(kind, showFn) {
      if (shell._overlayKind === kind) shell.closeOverlay();
      else showFn();
    },
    showSessions() {
      const groups = {};
      (shell._sessions || []).forEach((s) => {
        (groups[s.agent] = groups[s.agent] || []).push(s);
      });
      const blocks = Object.keys(groups).map((agent) => {
        const rows = groups[agent].map((s) => {
          const dot = '<span class="dot ' + (s.running ? "busy" : "idle") + '"></span>';
          const when = (s.last_event_at || "").slice(11, 16);
          const cwd = s.cwd || "";
          return '<div class="ov-row static">' + dot +
            '<span class="ov-main"><span class="ov-sub">' +
            esc(s.session_id.slice(0, 8)) + " · " + when +
            (cwd ? " · " + esc(shortPath(cwd)) : "") + "</span></span>" +
            '<span class="ov-sub">' + (s.running ? "运行中" : "已完成") + "</span></div>";
        });
        return "<h4>" + esc(agent) + "</h4>" + rows.join("");
      });
      openOverlay("<h4>会话</h4>" +
        (blocks.length ? blocks.join("") : '<div class="ov-sub">还没有会话</div>'), "sessions");
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
        openOverlay("<h4>切换词书</h4>" + rows.join(""), "books");
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

    applyTheme() {
      document.body.classList.remove("theme-light", "theme-dark");
      if (prefs.theme !== "auto") document.body.classList.add("theme-" + prefs.theme);
    },

    showSettings() {
      const api = shell.api();
      if (!api) return;
      Promise.all([api.get_prefs(), api.get_settings(), api.get_agents()]).then(([p, s, agents]) => {
        prefs.auto_pronounce = !!p.auto_pronounce;
        prefs.theme = p.theme || "auto";
        const chip = (group, val, label, on) =>
          '<span class="chip' + (on ? " on" : "") + '" data-g="' + group +
          '" data-v="' + val + '">' + label + "</span>";
        const num = (key, val, unit) =>
          '<span class="set-chips"><span class="num-btn" data-num="' + key +
          '" data-d="-1">−</span><span class="num-val" id="nv-' + key +
          '" data-key="' + key + '" title="点击直接输入">' +
          val + (unit || "") + '</span><span class="num-btn" data-num="' + key +
          '" data-d="1">+</span></span>';
        openOverlay(
          "<h4>设置</h4>" +
          '<div class="set-row"><span class="set-label">主题</span><span class="set-chips">' +
          chip("theme", "auto", "自动", prefs.theme === "auto") +
          chip("theme", "light", "日间", prefs.theme === "light") +
          chip("theme", "dark", "夜间", prefs.theme === "dark") + "</span></div>" +
          '<div class="set-row"><span class="set-label">自动发音</span><span class="set-chips">' +
          chip("sound", "1", "开", prefs.auto_pronounce) +
          chip("sound", "0", "关", !prefs.auto_pronounce) + "</span></div>" +
          '<div class="set-row"><span class="set-label">自动唤醒(agent 运行时弹出)</span><span class="set-chips">' +
          chip("autopop", "1", "开", !!s.auto_popup) +
          chip("autopop", "0", "关", !s.auto_popup) + "</span></div>" +
          '<div class="set-row"><span class="set-label">手动唤醒</span>' +
          '<span class="ov-sub">' + (s.hotkey || "热键不可用(组合键全被占用)") + "</span></div>" +
          '<div class="set-row"><span class="set-label">词书模式(进度保留)</span><span class="set-chips">' +
          chip("mode", "sequential", "顺序", s.mode === "sequential") +
          chip("mode", "shuffled", "乱序", s.mode === "shuffled") + "</span></div>" +
          '<div class="set-row"><span class="set-label">每日目标</span>' +
          num("daily_goal", s.daily_goal) + "</div>" +
          '<div class="set-row"><span class="set-label">弹出延迟</span>' +
          num("popup_delay_sec", s.popup_delay_sec, "s") + "</div>" +
          "<h4>Agent 接入</h4>" +
          (agents || []).map((a) => {
            let right;
            if (a.status === "connected") {
              right = '<span class="ag-ok">' + esc(a.detail) + "</span>" +
                (a.agent in { "claude-code": 1, codex: 1, workbuddy: 1 }
                  ? ' <span class="ag-btn" data-agent="' + a.agent + '" data-act="uninstall">移除</span>'
                  : "");
            } else if (a.status === "available") {
              right = '<span class="ag-btn" data-agent="' + a.agent + '" data-act="install">接入</span>';
            } else {
              right = '<span class="ov-sub">' + esc(a.detail) + "</span>";
            }
            return '<div class="set-row"><span class="set-label">' +
              esc(shortAgent(a.agent)) + '</span><span class="set-chips">' + right + "</span></div>";
          }).join(""),
          "settings"
        );
        shell._settingsCache = s;
        el("overlay").querySelectorAll(".chip").forEach((c) => {
          c.addEventListener("click", () => shell._onSettingChip(
            c.getAttribute("data-g"), c.getAttribute("data-v")));
        });
        el("overlay").querySelectorAll(".num-btn").forEach((b) => {
          b.addEventListener("click", () => shell._onSettingNum(
            b.getAttribute("data-num"), parseInt(b.getAttribute("data-d"), 10)));
        });
        el("overlay").querySelectorAll(".num-val").forEach((n) => {
          n.addEventListener("click", () => shell._editNum(n.getAttribute("data-key")));
        });
        el("overlay").querySelectorAll(".ag-btn").forEach((b) => {
          b.addEventListener("click", () => {
            const agent = b.getAttribute("data-agent");
            const isInstall = b.getAttribute("data-act") === "install";
            b.textContent = "…";
            const call = isInstall ? api.install_agent(agent) : api.uninstall_agent(agent);
            call.then(() => shell.showSettings());
          });
        });
      });
    },
    _editNum(key) {
      const api = shell.api();
      const s = shell._settingsCache;
      const node = el("nv-" + key);
      if (!api || !s || !node) return;
      node.innerHTML = '<input class="num-input" id="ni-' + key +
        '" type="number" value="' + s[key] + '">';
      const inp = el("ni-" + key);
      inp.focus();
      let isDone = false;
      const commitVal = () => {
        if (isDone) return;
        isDone = true;
        const v = parseInt(inp.value, 10);
        if (isNaN(v)) {
          if (shell.isOverlayOpen()) shell.showSettings();
          return;
        }
        api.set_setting(key, v).then((r) => {
          if (r.ok) s[key] = r.value;
          shell.updateStatus();
          if (shell.isOverlayOpen()) shell.showSettings();
        });
      };
      inp.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "Enter") commitVal();
      });
      inp.addEventListener("blur", commitVal);
    },
    _onSettingChip(group, val) {
      const api = shell.api();
      if (!api) return;
      if (group === "theme") {
        prefs.theme = val;
        shell.applyTheme();
        api.set_pref("theme", val).then(() => shell.showSettings());
      } else if (group === "sound") {
        prefs.auto_pronounce = val === "1";
        api.set_pref("auto_pronounce", prefs.auto_pronounce).then(() => shell.showSettings());
      } else if (group === "autopop") {
        api.set_setting("auto_popup", val === "1").then(() => shell.showSettings());
      } else if (group === "mode") {
        api.set_book_mode(val).then(() => {
          shell.updateStatus();
          panels.forEach((p) => p.refresh && p.refresh());
          shell.showSettings();
        });
      }
    },
    _onSettingNum(key, dir) {
      const api = shell.api();
      const s = shell._settingsCache;
      if (!api || !s) return;
      const step = key === "daily_goal" ? 10 : 2;
      api.set_setting(key, s[key] + dir * step).then((r) => {
        if (r.ok) {
          s[key] = r.value;
          const node = el("nv-" + key);
          if (node) node.textContent = r.value + (key === "popup_delay_sec" ? "s" : "");
          shell.updateStatus();
        }
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

  function openOverlay(html, kind) {
    const ov = el("overlay");
    ov.innerHTML = html;
    ov.classList.remove("hidden");
    shell._overlayKind = kind || null;
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
  function shortAgent(name) {
    return name === "claude-code" ? "claude" : name;
  }

  window.shell = shell;

  // Esc 分层:覆盖层 → 复习/浏览退出 → 当前词记 skip 并隐藏。捕获阶段监听。
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

  // 键盘焦点指示:有焦点才显示打字光标(kb-focus 门控 caret 的 CSS)
  const syncFocus = () => {
    document.body.classList.toggle("kb-focus", document.hasFocus());
  };
  window.addEventListener("focus", syncFocus);
  window.addEventListener("blur", syncFocus);
  syncFocus();

  window.addEventListener("pywebviewready", () => {
    el("btn-close").addEventListener("click", () => shell.escape());
    el("status-agents").addEventListener("click", () =>
      shell.toggleOverlay("sessions", shell.showSessions));
    el("status-text").addEventListener("click", () =>
      shell.toggleOverlay("books", shell.showBooks));
    el("btn-review").addEventListener("click", () => shell.startReview());
    el("btn-settings").addEventListener("click", () =>
      shell.toggleOverlay("settings", shell.showSettings));
    const apiNow = shell.api();
    if (apiNow && apiNow.get_prefs) {
      apiNow.get_prefs().then((p) => {
        prefs.auto_pronounce = !!p.auto_pronounce;
        prefs.theme = p.theme || "auto";
        shell.applyTheme();
      }).catch(() => shell.applyTheme());
    } else { shell.applyTheme(); }
    panels.forEach((p) => p.mount && p.mount());
    shell.updateStatus();
    shell.updateAgents();
    setInterval(shell.updateAgents, 3000);
  });
})();
