# WordGap hook script for Claude Code (and Claude-Code-compatible agents).
# Reads hook JSON from stdin, extracts session_id, reports the event to the
# local WordGap daemon. Must NEVER slow down or break the agent:
# catch-all, 1s timeout, always exit 0 (spec section 7.7).
param(
    [string]$Event = "done",
    [string]$Agent = "claude-code",
    [int]$Port = 8765
)
try {
    $sid = "unknown"
    $raw = [Console]::In.ReadToEnd()
    if ($raw) {
        $obj = $raw | ConvertFrom-Json
        if ($obj.session_id) { $sid = [string]$obj.session_id }
    }
    $body = @{ agent = $Agent; session_id = $sid; event = $Event } | ConvertTo-Json -Compress
    Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$Port/event" `
        -ContentType "application/json" -Body $body -TimeoutSec 1 | Out-Null
} catch { }
exit 0
