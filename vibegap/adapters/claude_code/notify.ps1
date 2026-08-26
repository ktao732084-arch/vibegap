# VibeGap hook for Claude-Code-compatible agents. Must never block or break
# the agent: bounded stdin read, 1s HTTP timeout, catch-all, always exit 0.
param(
    [string]$Event = "done",
    [string]$Agent = "claude-code",
    [int]$Port = 8765
)
try {
    $sid = "unknown"
    $reader = New-Object System.IO.StreamReader([Console]::OpenStandardInput())
    $task = $reader.ReadToEndAsync()
    if ($task.Wait(1000) -and $task.Result) {
        $obj = $task.Result | ConvertFrom-Json
        if ($obj.session_id) { $sid = [string]$obj.session_id }
    }
    $body = @{ agent = $Agent; session_id = $sid; event = $Event } | ConvertTo-Json -Compress
    Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$Port/event" `
        -ContentType "application/json" -Body $body -TimeoutSec 1 | Out-Null
} catch { }
exit 0
