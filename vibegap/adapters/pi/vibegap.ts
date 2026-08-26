// VibeGap pi extension: report turn lifecycle to the local VibeGap daemon.
// Install: copy this file into pi's extensions directory (see pi docs, hooks.md).
// NOTE: written against pi-mono extension API docs; not yet live-tested (no pi
// on the dev machine). Event names to verify on first real install: turn_start,
// agent_end. Must never break pi: fire-and-forget fetch, 1s timeout, no throws.
export default function vibegap(pi: any) {
  const PORT = 8765;
  const post = (event: string) => {
    try {
      const body = JSON.stringify({
        session_id: String(pi?.session?.id ?? "pi-session"),
        cwd: typeof process !== "undefined" ? process.cwd() : "",
      });
      fetch(`http://127.0.0.1:${PORT}/hook/pi/${event}?src=vibegap`, {
        method: "POST",
        body,
        signal: AbortSignal.timeout(1000),
      }).catch(() => {});
    } catch {
      /* never break the agent */
    }
  };
  pi.on("turn_start", () => post("running"));
  pi.on("agent_end", () => post("done"));
}
