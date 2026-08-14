# ============================================================
# netcheck-platform 数据备份（Windows PowerShell）
# 备份 SQLite 数据库、巡检报告目录与日志目录到一个带时间戳的目录，
# 并清理超过保留天数的旧备份。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1
#
# 可覆盖环境变量：
#   NETCHECK_DATA_DIR    数据库所在目录（默认 .\backend\data）
#   NETCHECK_REPORTS_DIR 报告目录（默认 同数据目录\reports）
#   NETCHECK_BACKUPS_DIR 备份输出目录（默认 .\backups）
#   NETCHECK_KEEP_DAYS   保留天数（默认 30）
# ============================================================
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$DataDir = if ($env:NETCHECK_DATA_DIR) { $env:NETCHECK_DATA_DIR } else { Join-Path $Root "backend\data" }
$ReportsDir = if ($env:NETCHECK_REPORTS_DIR) { $env:NETCHECK_REPORTS_DIR } else { Join-Path $DataDir "reports" }
$BackupsDir = if ($env:NETCHECK_BACKUPS_DIR) { $env:NETCHECK_BACKUPS_DIR } else { Join-Path $Root "backups" }
$KeepDays = if ($env:NETCHECK_KEEP_DAYS) { [int]$env:NETCHECK_KEEP_DAYS } else { 30 }

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$DestDir = Join-Path $BackupsDir $Stamp
New-Item -ItemType Directory -Force -Path $DestDir | Out-Null

$DbFile = Join-Path $DataDir "netcheck.db"
if (Test-Path $DbFile) {
  Copy-Item $DbFile (Join-Path $DestDir "netcheck.db")
  foreach ($ext in @("-wal", "-shm")) {
    $side = "$DbFile$ext"
    if (Test-Path $side) { Copy-Item $side (Join-Path $DestDir ("netcheck.db" + $ext)) }
  }
} else {
  Write-Host "警告：未找到数据库文件 $DbFile ，跳过数据库备份"
}

if (Test-Path $ReportsDir) {
  Copy-Item -Recurse $ReportsDir (Join-Path $DestDir "reports")
} else {
  Write-Host "警告：未找到报告目录 $ReportsDir ，跳过报告备份"
}

$Archive = Join-Path $BackupsDir "$Stamp.zip"
Compress-Archive -Path (Join-Path $DestDir "*") -DestinationPath $Archive -Force
Remove-Item -Recurse -Force $DestDir

Write-Host "备份完成：$Archive"
Write-Host "恢复方式：停止后端后，解压归档，netcheck.db（及其 -wal/-shm）放回 $DataDir，reports 放回 $ReportsDir。"

Get-ChildItem $BackupsDir -Filter "*.zip" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) } | Remove-Item -Force
Write-Host "已清理 $KeepDays 天前的旧备份。"