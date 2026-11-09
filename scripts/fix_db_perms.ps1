# 修复 PostgreSQL 权限脚本（需以管理员身份运行）
# 根因：之前的 DROP SCHEMA public CASCADE + CREATE SCHEMA public
# 重建后所有表的 owner 变成 postgres，forge 用户丢失了表级权限。
$ErrorActionPreference = "Continue"

$pgData = "D:\Program Files\PostgreSQL\15\data"
$psql = "D:\Program Files\PostgreSQL\15\bin\psql.exe"
$pgCtl = "D:\Program Files\PostgreSQL\15\bin\pg_ctl.exe"
$hba = Join-Path $pgData "pg_hba.conf"

Write-Host "=== Step 1: 备份 pg_hba.conf ===" -ForegroundColor Cyan
Copy-Item $hba "$hba.bak.permfix" -Force
Write-Host "Backup created."

Write-Host "=== Step 2: 切换到 trust 认证 ===" -ForegroundColor Cyan
$content = Get-Content $hba -Raw -Encoding UTF8
$content = $content -replace '(?m)^local\s+all\s+all\s+scram-sha-256', 'local   all             all                                     trust'
$content = $content -replace '(?m)^host\s+all\s+all\s+127\.0\.0\.1/32\s+scram-sha-256', 'host    all             all             127.0.0.1/32            trust'
Set-Content $hba $content -Encoding UTF8 -NoNewline
Write-Host "pg_hba.conf updated to trust."

Write-Host "=== Step 3: Reload PostgreSQL 配置 ===" -ForegroundColor Cyan
& $pgCtl reload -D $pgData -w
Start-Sleep -Seconds 2
Write-Host "Reload done."

Write-Host "=== Step 4: 修复表权限 ===" -ForegroundColor Cyan
$env:PGPASSWORD = ""
$fixSql = @"
GRANT ALL ON SCHEMA public TO forge;
GRANT ALL ON ALL TABLES IN SCHEMA public TO forge;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO forge;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO forge;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO forge;
"@

$result = $fixSql | & $psql -U postgres -h 127.0.0.1 -d forge 2>&1
Write-Host "GRANT result: $result"

Write-Host "=== Step 5: 验证修复 ===" -ForegroundColor Cyan
$verify = & $psql -U forge -h 127.0.0.1 -d forge -c "SELECT COUNT(*) FROM users WHERE email_normalized='admin@forge.local'" 2>&1
Write-Host "forge query result: $verify"

Write-Host "=== Step 6: 恢复 scram-sha-256 ===" -ForegroundColor Cyan
Copy-Item "$hba.bak.permfix" $hba -Force
Write-Host "pg_hba.conf restored from backup."

Write-Host "=== Step 7: Reload again ===" -ForegroundColor Cyan
& $pgCtl reload -D $pgData -w
Write-Host "Reload done."

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Green
Write-Host "You can now close this window."
Write-Host ""
Read-Host "Press Enter to close"
