/* 条带面板:AIHOT 新闻轮播。region: strip;拿不到数据时整条隐藏。
   标题过长时来回滚动展示全文;来源省略,显示相对时间。 */
(function () {
  "use strict";

  var ROTATE_MS = 12000;
  var strip = document.getElementById("panel-strip");
  var items = [];
  var index = 0;
  var timer = null;

  function relTime(iso) {
    if (!iso) return "";
    var t = Date.parse(iso);
    if (isNaN(t)) return "";
    var mins = Math.floor((Date.now() - t) / 60000);
    if (mins < 1) return "刚刚";
    if (mins < 60) return mins + "分钟前";
    var hours = Math.floor(mins / 60);
    if (hours < 24) return hours + "小时前";
    return Math.floor(hours / 24) + "天前";
  }

  function esc(s) {
    var div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  function show() {
    if (!items.length) { strip.classList.add("hidden"); return; }
    var item = items[index % items.length];
    var when = relTime(item.published_at);
    strip.innerHTML =
      '<span class="nt-wrap"><span class="nt-time">' + esc(when || "AI快讯") +
      "</span>" + esc(item.title) + "</span>";
    strip.classList.remove("hidden");
    requestAnimationFrame(function () {
      var wrap = strip.querySelector(".nt-wrap");
      if (!wrap) return;
      var overflow = wrap.scrollWidth - strip.clientWidth;
      if (overflow > 4) {
        // 超宽:来回滚动展示全文,速度恒定(约 40px/s),轮换周期随之拉长
        var dur = Math.max(4, overflow / 40);
        wrap.style.setProperty("--nt-dist", -overflow + "px");
        wrap.style.setProperty("--nt-dur", dur + "s");
        wrap.classList.add("scroll");
        resetTimer(Math.max(ROTATE_MS, dur * 2000 + 2000));
      } else {
        resetTimer(ROTATE_MS);
      }
    });
  }

  function resetTimer(ms) {
    if (timer) clearTimeout(timer);
    if (items.length > 1) timer = setTimeout(function () { index += 1; show(); }, ms);
  }

  function load() {
    var api = window.shell.api();
    if (!api) return;
    api.get_news().then(function (news) {
      items = news || [];
      index = 0;
      show();
    });
  }

  window.shell.register({
    id: "news-ticker",
    region: "strip",
    mount: function () { load(); },
    refresh: function () { load(); },
  });
})();
