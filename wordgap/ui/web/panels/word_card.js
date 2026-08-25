/* 主面板:qwerty 式打字背单词 + ←→ 浏览 + 错词复习。region: main */
(function () {
  "use strict";

  const root = document.getElementById("panel-main");
  let word = null;        // 当前显示的词
  let typed = 0;
  let typos = 0;
  let revealed = false;  // 当前是否显示答案(Tab 开关)
  let peeked = false;    // 本词是否看过答案(看过即记 fail)
  let busy = false;
  let browseOffset = 0;   // 0=正常打字;≠0=浏览模式(只读)
  let review = null;      // null=正常;{queue:[], idx:0}=复习模式

  function isBrowsing() { return browseOffset !== 0; }
  function isReview() { return review !== null; }

  function escText(s) {
    const div = document.createElement("div");
    div.textContent = s == null ? "" : String(s);
    return div.innerHTML;
  }

  function render() {
    if (!word) return;
    const showAll = isBrowsing() || revealed;
    const chars = word.name.split("").map((c, i) => {
      let cls = i < typed ? "ch ok" : showAll ? "ch reveal" : "ch";
      if (i === typed && !isBrowsing()) cls += " cur";  // 闪烁光标:当前待输入位
      const shown = i < typed || showAll ? c : " ";
      return '<span class="' + cls + '">' + shown + "</span>";
    }).join("");
    const transFull = word.trans.join(";");
    const transShort = transFull.length > 64 ? transFull.slice(0, 64) + "…" : transFull;
    let hint;
    if (isBrowsing()) {
      hint = "浏览 " + (browseOffset > 0 ? "+" : "") + browseOffset +
        " · ←→ 翻看 · 回车返回当前词";
    } else if (isReview()) {
      hint = "复习 " + (review.idx + 1) + "/" + review.queue.length +
        " · Tab 看答案 · Esc 退出复习";
    } else {
      hint = "敲出单词 · ←→ 看前后词 · Tab 看答案 · Esc 隐藏";
    }
    root.innerHTML =
      '<div class="wc-word" id="wc-word">' + chars + "</div>" +
      '<div class="wc-trans" title="' + escText(transFull) + '">' + escText(transShort) + "</div>" +
      '<div class="wc-phone" id="wc-phone" title="点击发音">' +
      (word.usphone ? "/" + word.usphone + "/" : "") +
      ' <span class="wc-speaker">🔊</span></div>' +
      '<div class="wc-hint">' + hint + "</div>";
    const phone = document.getElementById("wc-phone");
    if (phone) phone.addEventListener("click", pronounce);
  }

  function pronounce() {
    if (!word) return;
    const url = "https://dict.youdao.com/dictvoice?audio=" +
      encodeURIComponent(word.name) + "&type=2";
    new Audio(url).play().catch(() => {
      try {
        const u = new SpeechSynthesisUtterance(word.name);
        u.lang = "en-US";
        speechSynthesis.cancel();
        speechSynthesis.speak(u);
      } catch (e) { /* 无声降级 */ }
    });
  }

  function setWord(w) {
    word = w; typed = 0; typos = 0; revealed = false; peeked = false;
    render();
    if (window.shell.prefs.auto_pronounce) pronounce();
  }

  function load() {
    const api = window.shell.api();
    if (!api) return;
    busy = true;
    browseOffset = 0;
    api.next_word().then((w) => {
      busy = false;
      if (w.error) {
        root.innerHTML = '<div class="wc-trans">' +
          (w.error === "no_wordbook" ? "还没有词书,先导入一本" : w.error) + "</div>";
        word = null;
        return;
      }
      setWord(w);
    });
  }

  function browse(delta) {
    const api = window.shell.api();
    if (!api || busy) return;
    const target = browseOffset + delta;
    if (target === 0) { load(); return; }
    busy = true;
    api.peek_word(target).then((w) => {
      busy = false;
      if (w.error) return; // 越界:停在边缘
      browseOffset = target;
      word = w; typed = 0; typos = 0; revealed = false;
      render();
    });
  }

  function commit(result) {
    const api = window.shell.api();
    if (!api || !word) return;
    busy = true;
    if (isReview()) {
      api.log_review(review.queue[review.idx].word_index, result, typos).then(() => {
        busy = false;
        review.idx += 1;
        if (review.idx >= review.queue.length) {
          const n = review.queue.length;
          review = null;
          root.innerHTML = '<div class="wc-summary"><div class="big">复习完成</div>' +
            '<div class="sub">过了 ' + n + " 个错词</div></div>";
          setTimeout(load, 1600);
        } else {
          setWord(review.queue[review.idx]);
        }
        window.shell.updateStatus();
      });
      return;
    }
    api.commit_word(result, typos).then(() => {
      busy = false;
      window.shell.state.sessionWords += 1;
      window.shell.updateStatus();
      if (!window.shell.state.softClosing) load();
      // softClosing 时不加载下一词:Python 侧会推进到小结(onSummary)
    });
  }

  function onKey(e) {
    if (busy) return;
    if (e.key === "ArrowLeft" && !isReview()) { e.preventDefault(); browse(-1); return; }
    if (e.key === "ArrowRight" && !isReview()) { e.preventDefault(); browse(1); return; }
    if (isBrowsing()) {
      if (e.key === "Enter") { e.preventDefault(); load(); }
      return; // 浏览模式不接受打字
    }
    if (!word) return;
    if (e.key === "Tab") {
      e.preventDefault();
      revealed = !revealed;  // 再按一次收起答案
      if (revealed) peeked = true;
      typed = 0;
      render();
      return;
    }
    if (e.key.length !== 1 || !/[a-zA-Z'\- ]/.test(e.key)) return;
    e.preventDefault();
    if (revealed) revealed = false;  // 开始拼写,答案自动消失(peeked 仍记 fail)
    const expected = word.name[typed];
    if (e.key.toLowerCase() === expected.toLowerCase()) {
      typed += 1;
      if (typed >= word.name.length) {
        render();
        commit(peeked ? "fail" : "pass");
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
    refresh() { review = null; load(); },
    reset() { word = null; review = null; browseOffset = 0; root.innerHTML = ""; },
    handleEscape() {
      if (isReview()) { review = null; load(); return true; }
      if (isBrowsing()) { load(); return true; }
      return false;
    },
    startReview() {
      const api = window.shell.api();
      if (!api) return;
      api.get_review().then((queue) => {
        if (!queue.length) {
          root.innerHTML = '<div class="wc-summary"><div class="big">今日没有错词</div></div>';
          setTimeout(load, 1500);
          return;
        }
        review = { queue: queue, idx: 0 };
        browseOffset = 0;
        setWord(queue[0]);
      });
    },
    showSummary(sessionWords) {
      const api = window.shell.api();
      root.innerHTML =
        '<div class="wc-summary"><div class="big">本轮背了 ' + sessionWords + " 个词</div>" +
        '<div class="sub" id="wc-sum-sub"></div></div>';
      if (api) api.get_progress().then((p) => {
        const sub = document.getElementById("wc-sum-sub");
        if (sub && !p.error) {
          sub.textContent = "累计 " + p.cursor + "/" + p.total + " · " + p.book_name +
            " · 今日 " + p.today + "/" + p.goal;
        }
      });
    },
  });
})();
