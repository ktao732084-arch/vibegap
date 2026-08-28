/** dsh-vibegap browser half: a self-contained spelling card for dsh web. */
window.__ModuleLoader__.load({
  id: "dsh-vibegap",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
    var React = require("react");
    var primitives = require("@deepseek-ai/dsh-client-ui-primitives");
    var runtime = require("@deepseek-ai/dsh-client-runtime/client");

    var POPUP_DELAY_MS = 18000;
    var SUMMARY_LINGER_MS = 2000;
    var WORD_COMMIT_DELAY_MS = 240;
    var SHAKE_MS = 300;
    var DOWNLOAD_TIMEOUT_MS = 30000;
    var AUDIO_TIMEOUT_MS = 6000;
    var TRANSLATION_MAX_CHARS = 100;
    var DAEMON_URL = "http://127.0.0.1:8765/panel";
    var DAEMON_TIMEOUT_MS = 1000;
    var DAEMON_PROBE_MS = 5000;
    var DICT_URL = "https://raw.githubusercontent.com/RealKai42/qwerty-learner/master/public/dicts/CET6_T.json";
    var STYLE_ID = "vg-card-styles";
    var DONE_NOTICE = "会话已完成 · 拼完当前词后收起";
    var WAIT_NOTICE = "会话等待确认 · 拼完当前词后收起";
    var inject = ["slots"];
    var h = React.createElement;
    var Button = primitives.Button;
    var initialSeed = (Date.now() ^ 0x6d2b79f5) >>> 0;
    var progressStore = runtime.createSnapshotStore(
      { mode: "shuffle", seed: initialSeed, cursor: 0, words: null },
      { persist: { name: "vibegap.progress" } },
    );
    var prefsStore = runtime.createSnapshotStore(
      { autoPronounce: true },
      { persist: { name: "vibegap.prefs" } },
    );
    var posStore = runtime.createSnapshotStore(
      { x: null, y: null },
      { persist: { name: "vibegap.pos" } },
    );

    var css = [
      ".vg-card{position:fixed;right:24px;bottom:24px;width:min(390px,calc(100vw - 32px));box-sizing:border-box;padding:16px;border:1px solid var(--dsw-alias-border-l,#d8d8d8);border-radius:14px;background:var(--dsw-alias-bg-base,#fff);color:var(--dsw-alias-label-primary,#202020);box-shadow:0 12px 34px rgba(0,0,0,.18);font-family:inherit;pointer-events:auto;outline:none;z-index:1}",
      ".vg-card:focus{border-color:var(--dsw-alias-border-focus,#5794ff);box-shadow:0 12px 34px rgba(0,0,0,.18),0 0 0 2px rgba(87,148,255,.2)}",
      ".vg-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px;cursor:move;user-select:none;touch-action:none}",
      ".vg-title{font-size:13px;font-weight:650;letter-spacing:.02em}",
      ".vg-prog{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:right;font-size:11px;color:var(--dsw-alias-label-tertiary,#888)}",
      ".vg-close{min-width:28px!important;padding:0!important;font-size:18px!important}",
      ".vg-banner{margin:-2px 0 14px;padding:8px 10px;border-radius:8px;background:var(--dsw-alias-interactive-bg-hover,#f2f3f5);font-size:12px;line-height:1.4}",
      ".vg-word{display:flex;flex-wrap:wrap;justify-content:center;gap:4px;min-height:48px;margin:16px 0 12px}",
      ".vg-char{display:inline-flex;align-items:center;justify-content:center;width:24px;height:38px;border-bottom:2px solid var(--dsw-alias-border-l,#bbb);font:600 24px/1 ui-monospace,SFMono-Regular,Consolas,monospace}",
      ".vg-char-ok{color:var(--dsw-alias-state-success-primary,#238636);border-color:currentColor}",
      ".vg-char-reveal{color:var(--dsw-alias-label-secondary,#777)}",
      ".vg-char-cursor{animation:vg-blink 1s steps(1) infinite}",
      ".vg-trans{min-height:42px;text-align:center;color:var(--dsw-alias-label-secondary,#666);font-size:14px;line-height:1.5}",
      ".vg-meta{display:flex;align-items:center;justify-content:center;gap:8px;min-height:28px;margin-top:8px;color:var(--dsw-alias-label-tertiary,#888);font-size:12px}",
      ".vg-actions{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin-top:12px}",
      ".vg-hint{margin-top:12px;text-align:center;color:var(--dsw-alias-label-tertiary,#888);font-size:11px}",
      ".vg-empty{padding:18px 4px 8px;text-align:center;color:var(--dsw-alias-label-secondary,#666);font-size:13px;line-height:1.6}",
      ".vg-error{margin-top:10px;color:var(--dsw-alias-state-danger-primary,#c93c37);font-size:12px}",
      ".vg-shake{animation:vg-shake .28s ease-in-out}",
      "@keyframes vg-blink{50%{border-color:transparent}}",
      "@keyframes vg-shake{25%{transform:translateX(-5px)}75%{transform:translateX(5px)}}",
      "@media(max-width:520px){.vg-card{right:16px;bottom:16px}.vg-char{width:20px;font-size:21px}}",
    ].join("");

    function apply(ctx) {
      ctx.slots.inject("shell.overlay", function () {
        return ctx.slots.register(
          { name: "shell.overlay", id: "vibegap", order: 90000 },
          VibegapCard,
        );
      });
    }

    function identity(value) { return value; }

    function useSnapshot(store) {
      var state = React.useState(store.getSnapshot());
      React.useEffect(function () {
        return store.subscribe(function () { state[1](store.getSnapshot()); });
      }, [store]);
      return state[0];
    }
    function useCell(value) {
      return React.useState({ current: value })[0];
    }

    function mulberry32(seed) {
      return function random() {
        var value = seed += 0x6d2b79f5;
        value = Math.imul(value ^ value >>> 15, value | 1);
        value ^= value + Math.imul(value ^ value >>> 7, value | 61);
        return ((value ^ value >>> 14) >>> 0) / 4294967296;
      };
    }

    function shuffled(words, seed) {
      var result = words.slice();
      var random = mulberry32(seed >>> 0);
      for (var i = result.length - 1; i > 0; i -= 1) {
        var j = Math.floor(random() * (i + 1));
        var swap = result[i]; result[i] = result[j]; result[j] = swap;
      }
      return result;
    }

    function validWord(entry) {
      return entry && typeof entry.name === "string" && entry.name.length > 0 &&
        Array.isArray(entry.trans);
    }

    function normalizeWords(payload) {
      if (!Array.isArray(payload)) throw new Error("invalid wordbook");
      var words = payload.filter(validWord).map(function (entry) {
        return {
          name: entry.name,
          trans: entry.trans.filter(function (item) { return typeof item === "string"; }),
          usphone: typeof entry.usphone === "string" ? entry.usphone : "",
        };
      });
      if (words.length === 0) throw new Error("empty wordbook");
      return words;
    }

    function rootRows(state) {
      var rows = {};
      state.ids.forEach(function (id) {
        var row = state.byId[id];
        if (row && row.origin !== "subagent") rows[id] = row;
      });
      return rows;
    }

    function transitionNotice(previous, current) {
      var ids = Object.keys(current);
      for (var i = 0; i < ids.length; i += 1) {
        var row = current[ids[i]];
        var before = previous[ids[i]];
        if (!before) continue;
        if (!before.pendingInteraction && row.pendingInteraction) return WAIT_NOTICE;
        if (before.running && row.completed === true) return DONE_NOTICE;
      }
      return null;
    }

    function noticeStillActive(notice, rows) {
      return Object.keys(rows).some(function (id) {
        var row = rows[id];
        return notice === WAIT_NOTICE ? !!row.pendingInteraction : row.completed === true;
      });
    }

    function safePronounce(word) {
      try {
        var signal = AbortSignal.timeout(AUDIO_TIMEOUT_MS);
        var audio = new Audio("https://dict.youdao.com/dictvoice?audio=" +
          encodeURIComponent(word) + "&type=2");
        var stop = function () { try { audio.pause(); audio.removeAttribute("src"); } catch (_) {} };
        signal.addEventListener("abort", stop, { once: true });
        var played = audio.play();
        if (played && played.catch) played.catch(function () {});
      } catch (_) {}
    }

    async function downloadWords(setStatus) {
      setStatus({ busy: true, error: "" });
      try {
        var response = await fetch(DICT_URL, { signal: AbortSignal.timeout(DOWNLOAD_TIMEOUT_MS) });
        if (!response.ok) throw new Error("download failed");
        var words = normalizeWords(await response.json());
        progressStore.set({ mode: "shuffle", seed: initialSeed, cursor: 0, words: words });
        setStatus({ busy: false, error: "" });
      } catch (_) {
        setStatus({ busy: false, error: "下载失败，请检查网络后重试" });
      }
    }

    async function panelRequest(path, options) {
      var init = options || {};
      init.signal = AbortSignal.timeout(DAEMON_TIMEOUT_MS);
      var response = await fetch(DAEMON_URL + path, init);
      if (!response.ok) throw new Error("panel request failed");
      var payload = await response.json();
      if (payload.error) throw new Error(payload.error);
      return payload;
    }
    function syncLocalProgress(remoteProgress) {
      if (!remoteProgress || !Number.isFinite(Number(remoteProgress.cursor))) return;
      progressStore.update(function (draft) {
        if (!Array.isArray(draft.words) || draft.words.length === 0) return;
        if (Number(remoteProgress.total) !== draft.words.length) return;
        draft.cursor = Math.min(Math.max(Number(remoteProgress.cursor), 0), draft.words.length - 1);
      });
    }
    function useDaemonBackend() {
      var backend = React.useState({ mode: "probing", word: null });
      var current = useCell({ mode: "probing", word: null });
      var setBackend = function (next) { current.current = next; backend[1](next); };
      React.useEffect(function () {
        var active = true;
        var timer = null;
        async function probe() {
          try {
            var state = await panelRequest("/state");
            if (!state.ready) throw new Error("daemon has no wordbook");
            syncLocalProgress(state.progress);
            var cursor = state.progress && Number(state.progress.cursor);
            var known = current.current.word && Number(current.current.word.position);
            if (current.current.mode !== "daemon" || cursor !== known) {
              var word = await panelRequest("/next-word");
              if (active) setBackend({ mode: "daemon", word: word });
            }
          } catch (_) {
            if (active && current.current.mode !== "local") setBackend({ mode: "local", word: null });
          }
          if (active) timer = setTimeout(probe, DAEMON_PROBE_MS);
        }
        probe();
        return function () { active = false; if (timer) clearTimeout(timer); };
      }, []);
      return backend;
    }

    function advanceProgress(total) {
      progressStore.update(function (draft) {
        if (draft.cursor + 1 < total) { draft.cursor += 1; return; }
        draft.cursor = 0;
        draft.seed = (draft.seed + 0x9e3779b9) >>> 0;
      });
    }

    function LetterGrid(props) {
      var chars = props.word.split("");
      return h("div", { className: "vg-word" + (props.shaking ? " vg-shake" : "") },
        chars.map(function (char, index) {
          var shown = index < props.typed || props.revealed;
          var classes = "vg-char";
          if (index < props.typed) classes += " vg-char-ok";
          else if (props.revealed) classes += " vg-char-reveal";
          if (props.focused && index === props.typed && !props.revealed) classes += " vg-char-cursor";
          return h("span", { className: classes, key: index }, shown ? char : "\u00a0");
        }),
      );
    }

    function EmptyCard(props) {
      return h("div", { className: "vg-empty" },
        h("div", null, "首次使用需要下载词库（CET6，约 0.5MB）"),
        h("div", { className: "vg-actions" },
          h(Button, {
            variant: "primary", size: "sm", disabled: props.status.busy,
            onClick: function () { downloadWords(props.setStatus); },
          }, props.status.busy ? "正在下载" : "下载词库"),
        ),
        props.status.error ? h("div", { className: "vg-error", role: "alert" }, props.status.error) : null,
      );
    }

    function useLifecycle(sessionState, visible, setVisible, showBanner, onRestart) {
      var ref = useCell({ running: false, rows: {}, suppressed: false, arm: null, pending: null });
      var runningRef = useCell(false);
      var visibleRef = useCell(visible);
      React.useEffect(function () { visibleRef.current = visible; }, [visible]);
      React.useEffect(function () {
        var anyRunning = sessionState.ids.some(function (id) {
          var row = sessionState.byId[id]; return row && row.running;
        });
        var life = ref.current;
        runningRef.current = anyRunning;
        if (!life.running && anyRunning) {
          life.suppressed = false; life.pending = null;
          onRestart();
          if (!visibleRef.current) life.arm = setTimeout(function () {
            if (!runningRef.current || life.suppressed) return;
            setVisible(true);
            if (life.pending) { showBanner(life.pending); life.pending = null; }
          }, POPUP_DELAY_MS);
        }
        if (life.running && !anyRunning && life.arm) {
          clearTimeout(life.arm); life.arm = null; life.pending = null;
        }
        var rows = rootRows(sessionState);
        if (life.pending && !noticeStillActive(life.pending, rows)) life.pending = null;
        var notice = transitionNotice(life.rows, rows);
        if (notice && visibleRef.current && !life.suppressed) showBanner(notice);
        else if (notice && anyRunning && !life.suppressed) life.pending = notice;
        life.running = anyRunning;
        life.rows = rows;
      }, [sessionState]);
      React.useEffect(function () { return function () { if (ref.current.arm) clearTimeout(ref.current.arm); }; }, []);
      return { state: ref, running: runningRef };
    }

    function useTyping(config) {
      React.useEffect(function () {
        if (!config.visible || !config.focused || !config.word || config.busy) return;
        function onKey(event) {
          if (document.activeElement !== config.card.current) return;
          if (event.key === "Escape") { event.preventDefault(); config.hide(); return; }
          if (event.key === "Tab") {
            event.preventDefault(); config.setPeeked(true); config.setTyped(0);
            config.setRevealed(function (value) { return !value; }); return;
          }
          if (event.key.length !== 1 || !/[a-zA-Z'\- ]/.test(event.key)) return;
          event.preventDefault();
          if (config.revealed) config.setRevealed(false);
          if (event.key.toLowerCase() === config.word[config.typed].toLowerCase()) {
            var next = config.typed + 1; config.setTyped(next);
            if (next === config.word.length) config.complete();
            return;
          }
          config.setTypos(function (value) { return value + 1; });
          config.setTyped(0); config.shake();
        }
        document.addEventListener("keydown", onKey);
        return function () { document.removeEventListener("keydown", onKey); };
      }, [config]);
    }

    function CardBody(props) {
      if (!props.word) return h(EmptyCard, { status: props.download, setStatus: props.setDownload });
      var translation = props.word.trans.join("；");
      return h(React.Fragment, null,
        h(LetterGrid, {
          word: props.word.name, typed: props.typed, revealed: props.revealed,
          focused: props.focused, shaking: props.shaking,
        }),
        h("div", { className: "vg-trans", title: translation }, translation.slice(0, TRANSLATION_MAX_CHARS)),
        h("div", { className: "vg-meta" },
          props.word.usphone ? "/" + props.word.usphone + "/" : null,
          props.typos ? "错 " + props.typos : null,
          props.outcome ? h("span", { role: "status" }, props.outcome === "fail" ? "已记为需复习" : "拼写正确") : null,
        ),
        h("div", { className: "vg-actions" },
          h(Button, { size: "sm", variant: "outline", onClick: props.pronounce }, "发音"),
          h(Button, { size: "sm", variant: "ghost", onClick: props.toggleAuto },
            "自动发音：" + (props.autoPronounce ? "开" : "关")),
        ),
        h("div", { className: "vg-hint" }, "点击卡片后拼写 · Tab 查看答案 · Esc 隐藏"),
      );
    }

    function useCardStates() {
      return {
        visible: React.useState(false), banner: React.useState(null), focused: React.useState(false),
        typed: React.useState(0), typos: React.useState(0), revealed: React.useState(false),
        peeked: React.useState(false), shaking: React.useState(false), busy: React.useState(false),
        outcome: React.useState(""), holdWord: React.useState(null),
        download: React.useState({ busy: false, error: "" }),
        pos: React.useState(null),
      };
    }

    function useWordSelection(progress) {
      var words = progress && Array.isArray(progress.words) && progress.words.every(validWord) ? progress.words : null;
      var seed = progress && Number(progress.seed) || 0;
      var cache = useCell({ words: null, seed: null, ordered: [] });
      if (cache.current.words !== words || cache.current.seed !== seed) {
        cache.current = { words: words, seed: seed, ordered: words ? shuffled(words, seed) : [] };
      }
      var ordered = cache.current.ordered;
      var cursorValue = progress && Number(progress.cursor) || 0;
      var cursor = ordered.length ? Math.min(Math.max(cursorValue, 0), ordered.length - 1) : 0;
      return { ordered: ordered, word: ordered[cursor] || null };
    }
    function activeSelection(local, backend) {
      var remote = backend[0];
      if (remote.mode === "daemon" && remote.word) {
        return { ordered: [remote.word], word: remote.word, isDaemon: true };
      }
      return { ordered: local.ordered, word: local.word, isDaemon: false };
    }

    function useLifecycleBridge(sessionState, states, refs) {
      var showBanner = function (message) {
        refs.banner.current = message; states.banner[1](message);
      };
      var onRestart = function () {
        if (!refs.hideTimer.current) return;
        clearTimeout(refs.hideTimer.current); refs.hideTimer.current = null;
        showBanner(null); resetInput(states);
      };
      var tracker = useLifecycle(sessionState, states.visible[0], states.visible[1], showBanner, onRestart);
      return { tracker: tracker, showBanner: showBanner };
    }
    function resetInput(states) {
      states.typed[1](0); states.typos[1](0); states.revealed[1](false);
      states.peeked[1](false); states.busy[1](false); states.shaking[1](false);
      states.outcome[1](""); states.holdWord[1](null);
    }

    function hideCard(model, suppress) {
      if (model.refs.hideTimer.current) clearTimeout(model.refs.hideTimer.current);
      model.refs.hideTimer.current = null;
      var life = model.lifecycle.tracker.state.current;
      if (life.arm) clearTimeout(life.arm);
      life.arm = null;
      life.pending = null;
      if (suppress) life.suppressed = true;
      model.refs.banner.current = null; model.states.banner[1](null);
      model.states.visible[1](false); model.states.focused[1](false);
      resetInput(model.states);
    }

    function completeWord(model) {
      model.states.busy[1](true);
      model.states.outcome[1](model.states.peeked[0] ? "fail" : "pass");
      setTimeout(async function () {
        var shouldHide = !!model.refs.banner.current && !model.lifecycle.tracker.running.current;
        if (shouldHide) model.states.holdWord[1](model.selection.word);
        await advanceSelection(model);
        if (!model.refs.banner.current) { resetInput(model.states); return; }
        if (model.lifecycle.tracker.running.current) {
          model.lifecycle.showBanner(null); resetInput(model.states); return;
        }
        model.refs.hideTimer.current = setTimeout(function () {
          hideCard(model, false);
        }, SUMMARY_LINGER_MS);
      }, WORD_COMMIT_DELAY_MS);
    }
    async function advanceSelection(model) {
      if (!model.selection.isDaemon) {
        advanceProgress(model.selection.ordered.length); return;
      }
      try {
        var result = await panelRequest("/commit", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            result: model.states.peeked[0] ? "fail" : "pass",
            typo_count: model.states.typos[0],
          }),
        });
        syncLocalProgress(result);
        var word = await panelRequest("/next-word");
        model.backend[1]({ mode: "daemon", word: word });
      } catch (_) { model.backend[1]({ mode: "local", word: null }); }
    }

    function shakeCard(states) {
      states.shaking[1](true);
      setTimeout(function () { states.shaking[1](false); }, SHAKE_MS);
    }

    function startDrag(model, event) {
      if (event.target.closest("button,a,input,textarea,select")) return;
      var card = model.refs.card.current;
      if (!card || event.button !== 0) return;
      event.preventDefault();
      var rect = card.getBoundingClientRect();
      var offsetX = event.clientX - rect.left;
      var offsetY = event.clientY - rect.top;
      var last = null;
      function move(ev) {
        last = {
          x: Math.min(Math.max(ev.clientX - offsetX, 0), Math.max(window.innerWidth - rect.width, 0)),
          y: Math.min(Math.max(ev.clientY - offsetY, 0), Math.max(window.innerHeight - 48, 0)),
        };
        model.states.pos[1](last);
      }
      function up() {
        document.removeEventListener("pointermove", move);
        document.removeEventListener("pointerup", up);
        if (last) try { posStore.set(last); } catch (_) {}
      }
      document.addEventListener("pointermove", move);
      document.addEventListener("pointerup", up);
    }

    function useCardEffects(model) {
      var word = displayedWord(model);
      React.useEffect(function () { resetInput(model.states); }, [word && word.name]);
      React.useEffect(function () {
        if (model.states.visible[0] && word && model.autoPronounce) safePronounce(word.name);
      }, [model.states.visible[0], word && word.name, model.autoPronounce]);
      React.useEffect(function () {
        return function () { if (model.refs.hideTimer.current) clearTimeout(model.refs.hideTimer.current); };
      }, []);
      React.useEffect(function () {
        // 恢复上次拖到的位置;越出当前视口则放弃,回默认右下角
        try {
          var saved = posStore.getSnapshot();
          if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y) &&
              saved.x >= 0 && saved.y >= 0 &&
              saved.x < window.innerWidth - 60 && saved.y < window.innerHeight - 48) {
            model.states.pos[1]({ x: saved.x, y: saved.y });
          }
        } catch (_) {}
      }, []);
    }

    function useCardTyping(model) {
      var states = model.states;
      var word = displayedWord(model);
      useTyping({
        visible: states.visible[0], focused: states.focused[0],
        word: word && word.name,
        busy: states.busy[0], typed: states.typed[0], revealed: states.revealed[0],
        card: model.refs.card, setTyped: states.typed[1], setTypos: states.typos[1],
        setRevealed: states.revealed[1], setPeeked: states.peeked[1],
        hide: function () { hideCard(model, true); },
        complete: function () { completeWord(model); },
        shake: function () { shakeCard(states); },
      });
    }

    function renderCard(model) {
      var states = model.states;
      return h(React.Fragment, null, h("style", { id: STYLE_ID }, css),
        h("section", {
          className: "vg-card", tabIndex: 0, ref: model.refs.card, "aria-label": "VibeGap 单词卡",
          style: states.pos[0]
            ? { left: states.pos[0].x + "px", top: states.pos[0].y + "px", right: "auto", bottom: "auto" }
            : undefined,
          onFocus: function (event) { if (event.target === event.currentTarget) states.focused[1](true); },
          onBlur: function () { states.focused[1](false); },
          onMouseDown: function (event) {
            if (!event.target.closest("button,a,input,textarea,select")) model.refs.card.current.focus();
          },
        },
        h("div", {
          className: "vg-head", title: "按住拖动",
          onPointerDown: function (event) { startDrag(model, event); },
        },
          h("div", { className: "vg-title" }, "VibeGap"),
          model.progressText ? h("span", { className: "vg-prog" }, model.progressText) : null,
          h(Button, { className: "vg-close", size: "sm", variant: "ghost", title: "隐藏",
            onClick: function () { hideCard(model, true); } }, "×")),
        states.banner[0] ? h("div", { className: "vg-banner", role: "status" }, states.banner[0]) : null,
        h(CardBody, cardBodyProps(model))),
      );
    }

    function cardBodyProps(model) {
      var states = model.states;
      var word = displayedWord(model);
      return {
        word: word, typed: states.typed[0], typos: states.typos[0], revealed: states.revealed[0],
        focused: states.focused[0], shaking: states.shaking[0], download: states.download[0],
        outcome: states.outcome[0], setDownload: states.download[1], autoPronounce: model.autoPronounce,
        pronounce: function () { if (word) safePronounce(word.name); },
        toggleAuto: function () { prefsStore.set({ autoPronounce: !model.autoPronounce }); },
      };
    }
    function displayedWord(model) {
      return model.states.holdWord[0] || model.selection.word;
    }
    function VibegapCard(props) {
      var sessionState = props.useSessions(identity);
      var progress = useSnapshot(progressStore);
      var prefs = useSnapshot(prefsStore);
      var states = useCardStates();
      var refs = { card: useCell(null), hideTimer: useCell(null), banner: useCell(null) };
      var lifecycle = useLifecycleBridge(sessionState, states, refs);
      var backend = useDaemonBackend();
      var selection = activeSelection(useWordSelection(progress), backend);
      var word = selection.word;
      var progressText = "";
      if (selection.isDaemon && word && Number.isFinite(Number(word.total))) {
        progressText = word.position + "/" + word.total + " · 共享桌面进度";
      } else if (selection.ordered.length) {
        var cursorShown = Math.min(Math.max(Number(progress.cursor) || 0, 0), selection.ordered.length - 1);
        progressText = cursorShown + "/" + selection.ordered.length + " · 本地进度";
      }
      var model = {
        states: states, refs: refs, lifecycle: lifecycle, selection: selection, backend: backend,
        autoPronounce: !prefs || prefs.autoPronounce !== false,
        progressText: progressText,
      };
      useCardEffects(model);
      useCardTyping(model);
      return states.visible[0] ? renderCard(model) : h("style", { id: STYLE_ID }, css);
    }

    exports.apply = apply;
    exports.inject = inject;
    return module.exports;
  },
});
