$ErrorActionPreference = "Stop"
$base = if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8000" }

$health = curl.exe -fsS "$base/healthz"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output $health

$readyFile = Join-Path $env:TEMP "forge-ready.json"
$code = curl.exe -sS -o $readyFile -w "%{http_code}" "$base/readyz"
Write-Output (Get-Content -Raw $readyFile)
if ($code -ne "200" -and $code -ne "503") {
    Write-Error "readyz 返回了意外状态码 $code"
    exit 1
}
