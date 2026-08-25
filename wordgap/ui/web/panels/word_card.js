/* 主面板:qwerty 式打字背单词。region: main */
(function () {
  "use strict";

  const root = document.getElementById("panel-main");
  let word = null;      // {name, trans, usphone, position, total}
  let typed = 0;        // 已敲对的字母数
  let typos = 0;        // 本词敲错整词次数
  let revealed = false; // Tab 显示了答案(记 fail)
  let busy = false;

  function render() {
    if (!word) return;
    const chars = word.name
      .split("")
      .map((c, i) => {
        const cls = i < typed ? "ch ok" : revealed ? "ch reveal" : "ch";
        const shown = i < typed || revealed ? c : " ";
        return '<span class="' + cls + '">' + shown + "</span>";
      })
      .join("");
    root.innerHTML =
      '<div class="wc-word" id="wc-word">' + chars + "</div>" +
      '<div class="wc-trans">' + word.trans.join(";") + "</div>" +
      '<div class="wc-phone" id="wc-phone" title="点击发音">' +
      (word.usphone ? "/" + word.usphone + "/" : "") + ' <span class="wc-speaker">🔊</span></div>' +
      '<div class="wc-hint">敲出单词 · Tab 看答案 · Esc 隐藏</div>';
    const phone = document.getElementById("wc-phone");
    if (phone) phone.addEventListener("click", pronounce);
  }

  function pronounce() {
    if (!word) return;
    const url =
      "https://dict.youdao.com/dictvoice?audio=" +
      encodeURIComponent(word.name) + "&type=2";
    const player = new Audio(url);
    player.play().catch(() => {
      try {
        const u = new SpeechSynthesisUtterance(word.name);
        u.lang = "en-US";
        speechSynthesis.cancel();
        speechSynthesis.speak(u);
      } catch (e) { /* 无声降级 */ }
    });
  }

  function load() {
    const api = window.shell.api();
    if (!api) return;
    busy = true;
    api.next_word().then((w) => {
      busy = false;
      if (w.error) {
        root.innerHTML = '<div class="wc-trans">' +
          (w.error === "no_wordbook" ? "还没有词书,先导入一本" : w.error) + "</div>";
        return;
      }
      word = w; typed = 0; typos = 0; revealed = false;
      render();
      pronounce();
    });
  }

  function commit(result) {
    const api = window.shell.api();
    if (!api || !word) return;
    busy = true;
    api.commit_word(result, typos).then(() => {
      busy = false;
      window.shell.state.sessionWords += 1;
      window.shell.updateStatus();
      if (!window.shell.state.softClosing) load();
      // softClosing 时不加载下一词:Python 侧会推进到小结(onSummary)
    });
  }

  function onKey(e) {
    if (!word || busy) return;
    if (e.key === "Tab") {
      e.preventDefault();
      revealed = true; typed = 0;
      render();
      return;
    }
    if (e.key.length !== 1 || !/[a-zA-Z'\- ]/.test(e.key)) return;
    e.preventDefault();
    const expected = word.name[typed];
    if (e.key.toLowerCase() === expected.toLowerCase()) {
      typed += 1;
      if (typed >= word.name.length) {
        render();
        commit(revealed ? "fail" : "pass");
        return;
      }
    } else {
      typos += 1; typed = 0;
      const wordEl = document.getElementById("wc-word");
      if (wordEl) {
        wordEl.classList.add("shake");
        setTimeout(() => wordEl.classList.remove("shake"), 300);
      }
    }
    render();
  }

  window.shell.register({
    id: "word-card",
    region: "main",
    mount() {
      document.addEventListener("keydown", onKey);
      load();
    },
    refresh() { load(); },
    reset() { word = null; root.innerHTML = ""; },
    showSummary(sessionWords) {
      const api = window.shell.api();
      const done = () => {
        root.innerHTML =
          '<div class="wc-summary"><div class="big">本轮背了 ' + sessionWords + " 个词</div>" +
          '<div class="sub" id="wc-sum-sub"></div></div>';
        if (api) api.get_progress().then((p) => {
          const sub = document.getElementById("wc-sum-sub");
          if (sub && !p.error) sub.textContent = "累计 " + p.cursor + "/" + p.total + " · " + p.book_name;
        });
      };
      done();
    },
  });
})();
