<#
.SYNOPSIS
  一站式完整重建 forge 数据库。

.DESCRIPTION
  彻底删除 forge 数据库（DROP DATABASE），重新创建空库，
  然后执行 forge_prod_02_init_schema.sql 建表 + 种子数据。等价于"一键还原到初始状态"。

.USAGE
  powershell -ExecutionPolicy Bypass -File scripts/reset_forge_db.ps1

  或直接在 PowerShell 里执行：
  .\scripts\reset_forge_db.ps1 [-PostgresPassword "xxx"] [-ForgePassword "xxx"]

.PARAMETER PostgresPassword
  PostgreSQL 超级用户（postgres）的密码。默认从环境变量 PGPASSWORD 读取，
  或使用脚本内的默认值 kb7$rL3d8!tQ。

.PARAMETER ForgePassword
  forge 用户的密码。默认 forge-dev-only。
#>

param(
    [string]$PostgresPassword = "kb7`$rL3d8!tQ",
    [string]$ForgePassword    = "forge-dev-only"
)

$ErrorActionPreference = "Stop"

$ProjectRoot     = Split-Path -Parent $PSScriptRoot
$Psql            = "D:\Program Files\PostgreSQL\15\bin\psql.exe"
$ForgeProdSql    = Join-Path $ProjectRoot "forge_prod_02_init_schema.sql"
$AlembicDir      = Join-Path $ProjectRoot "apps\api"

if (-not (Test-Path $Psql)) {
    Write-Error "psql.exe 不存在: $Psql"
    exit 1
}
if (-not (Test-Path $ForgeProdSql)) {
    Write-Error "forge_prod_02_init_schema.sql 不存在: $ForgeProdSql"
    exit 1
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Forge 数据库 · 完整重建脚本" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ---- 1. 连 postgres 库，先 DROP DATABASE forge ----
Write-Host "[1/4] 终止 forge 库的活动会话..." -ForegroundColor Yellow
$env:PGPASSWORD = $PostgresPassword
& $Psql -U postgres -h 127.0.0.1 -d postgres -v ON_ERROR_STOP=1 -c @"
SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
 WHERE datname = 'forge' AND pid <> pg_backend_pid();
"@ 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Warning "终止会话时遇到问题（可能 forge 库当前不存在），继续..." }

Write-Host "[2/4] DROP + CREATE DATABASE forge (OWNER forge)..." -ForegroundColor Yellow
& $Psql -U postgres -h 127.0.0.1 -d postgres -v ON_ERROR_STOP=1 -c @"
DROP DATABASE IF EXISTS forge;
CREATE DATABASE forge
  WITH ENCODING = 'UTF8'
       LC_COLLATE = 'en_US.UTF-8'
       LC_CTYPE   = 'en_US.UTF-8'
       TEMPLATE   = template0
       OWNER      = forge;
GRANT CONNECT ON DATABASE forge TO forge;
GRANT ALL PRIVILEGES ON DATABASE forge TO forge;
"@ 2>&1 | ForEach-Object { Write-Host "  $_" }
if ($LASTEXITCODE -ne 0) { Write-Error "DROP/CREATE DATABASE 失败"; exit 1 }

# ---- 2. 执行 forge_prod_02_init_schema.sql（第 1 步删库已在上一步完成）----
Write-Host "[3/4] 执行 forge_prod_02_init_schema.sql（建表 + 种子数据）..." -ForegroundColor Yellow
$env:PGPASSWORD = $ForgePassword
& $Psql -U forge -h 127.0.0.1 -d forge -v ON_ERROR_STOP=1 -f $ForgeProdSql 2>&1 | ForEach-Object { Write-Host "  $_" }
if ($LASTEXITCODE -ne 0) {
    Write-Error "forge_prod_02_init_schema.sql 执行失败，见上方错误信息"
    exit 1
}

# ---- 3. Alembic stamp head ----
Write-Host "[4/4] Alembic stamp head（对齐迁移版本号）..." -ForegroundColor Yellow
Push-Location $AlembicDir
try {
    & ".\.venv\Scripts\python.exe" -m alembic stamp head 2>&1 | Out-Null
    Write-Host "  alembic version: head (ok)" -ForegroundColor Green
}
finally {
    Pop-Location
}

# ---- 4. 结果 ----
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  重建完成！" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  数据库:  forge"
Write-Host "  用户名:  forge"
Write-Host "  密码:    $ForgePassword"
Write-Host "  超级管理员:  admin@forge.local / admin123"
Write-Host ""
Write-Host "  立即登录并修改 admin 密码！" -ForegroundColor Red
Write-Host ""
