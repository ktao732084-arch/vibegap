/* 条带面板:AIHOT 新闻轮播。region: strip;拿不到数据时整条隐藏。 */
(function () {
  "use strict";

  const ROTATE_MS = 8000;
  const strip = document.getElementById("panel-strip");
  let items = [];
  let index = 0;
  let timer = null;

  function show() {
    if (!items.length) { strip.classList.add("hidden"); return; }
    const item = items[index % items.length];
    strip.innerHTML =
      '<span class="nt-item"><span class="nt-src">' + esc(item.source || "AI快讯") +
      "</span>" + esc(item.title) + "</span>";
    strip.classList.remove("hidden");
  }

  function esc(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  function rotate() { index += 1; show(); }

  function load() {
    const api = window.shell.api();
    if (!api) return;
    api.get_news().then((news) => {
      items = news || [];
      index = 0;
      show();
      if (timer) clearInterval(timer);
      if (items.length > 1) timer = setInterval(rotate, ROTATE_MS);
    });
  }

  window.shell.register({
    id: "news-ticker",
    region: "strip",
    mount() { load(); },
    refresh() { load(); },
  });
})();
