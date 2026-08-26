"use strict";
// dsh-wordgap: report agent turn lifecycle to the local WordGap daemon.
// Fire-and-forget, 1s timeout, catch-all -- must never break the harness.
// Plain CJS on purpose: no build step, installable via `link:` directly.

const PORT = 8765;

exports.name = "dsh-wordgap";

function post(event, sessionId, cwd) {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 1000);
    fetch(`http://127.0.0.1:${PORT}/hook/dsh/${event}?src=wordgap`, {
      method: "POST",
      body: JSON.stringify({
        session_id: String(sessionId || "dsh-session"),
        cwd: String(cwd || ""),
      }),
      signal: controller.signal,
    })
      .catch(() => {})
      .finally(() => clearTimeout(timer));
  } catch {
    /* never break the harness */
  }
}

exports.apply = function apply(ctx) {
  const sid = (s) => (s && (s.id || s.sessionId || s.session_id)) || "dsh-session";
  const dir = (s) => (s && (s.cwd || s.workdir)) || "";
  // TODO(装机实测校准): 'session/created' 见于官方教程,turn 级事件名
  // (turn/start、turn/end 或 pre-step / turn-end)以实际 dsh 版本为准 --
  // 安装后开 debug 日志确认一次即可,只改这三行。
  ctx.on("turn/start", (s) => post("running", sid(s), dir(s)));
  ctx.on("turn/end", (s) => post("done", sid(s), dir(s)));
  ctx.on("session/completed", (s) => post("done", sid(s), dir(s)));
};
