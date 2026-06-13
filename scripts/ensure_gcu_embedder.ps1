# Ensure the GCU embedding model is loaded in LM Studio (port 1234).
# LM Studio reloads only the CHAT model on boot, not the embedder, so after a
# reboot find_indicator / search_knowledge fail with HTTP 400. This closes that
# gap. Idempotent (lms load is a no-op if already loaded); no --ttl so the model
# stays resident. Intended to run on logon via Task Scheduler.
$ErrorActionPreference = 'SilentlyContinue'
$lms   = Join-Path $env:USERPROFILE '.lmstudio\bin\lms.exe'
$model = 'text-embedding-multilingual-e5-large-instruct'
$emb   = 'http://127.0.0.1:1234/v1/embeddings'
$log   = Join-Path $PSScriptRoot 'ensure_gcu_embedder.log'

function Log($m) { "$([DateTime]::Now.ToString('s')) $m" | Out-File -Append -Encoding utf8 $log }

Log "start"

# 1) Probe the embeddings endpoint. If it already answers, nothing to do.
function Test-Embed {
    try {
        $body = @{ model = $model; input = @('ping') } | ConvertTo-Json
        $r = Invoke-RestMethod -Uri $emb -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 20
        return ($r.data[0].embedding.Count -gt 0)
    } catch { return $false }
}

if (Test-Embed) { Log "already loaded, ok"; exit 0 }

# 2) Wait up to 3 min for the LM Studio server to be up after boot.
for ($i = 0; $i -lt 36; $i++) {
    $st = & $lms server status 2>$null
    if ($st -match 'running') { break }
    Start-Sleep -Seconds 5
}

# 3) Load the embedder (no-op if already loaded), then verify.
& $lms load $model -y 2>&1 | Out-File -Append -Encoding utf8 $log
Start-Sleep -Seconds 3

if (Test-Embed) { Log "loaded ok"; exit 0 }
else            { Log "FAILED to load"; exit 1 }
