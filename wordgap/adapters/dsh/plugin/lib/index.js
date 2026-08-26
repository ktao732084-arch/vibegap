"use strict";
// dsh-wordgap: report agent lifecycle to the local WordGap daemon.
// Event contract source-verified against deepseek-harness (2026-08-26):
//   packages/core/agent/src/runtime-types.ts
//     'agent/status'(payload: { agent: Agent; status: AgentStatus }): void
//     AgentStatus = 'idle' | 'running'  (emitted on every transition)
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
  ctx.on(
    "agent/status",
    function onStatus(payload) {
      const agent = payload && payload.agent;
      const sid = (agent && agent.session && agent.session.id) || "dsh-session";
      // TODO(装机确认): cwd 字段名 -- AgentOptions 里按 cwd/workspace 双名兼容取
      const opts = (agent && agent.options) || {};
      const cwd = opts.cwd || opts.workspace || "";
      post(payload.status === "running" ? "running" : "done", sid, cwd);
    },
    { global: true },
  );
};
