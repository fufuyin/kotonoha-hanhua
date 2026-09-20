# Install / rollback the asset-level font fix (spliced sharedassets0.assets).
#   powershell -File install_assetfix.ps1              # install (auto-backup)
#   powershell -File install_assetfix.ps1 -Uninstall   # restore newest backup
#   powershell -File install_assetfix.ps1 -List        # list backups
# ASCII-only on purpose: PowerShell 5.1 reads BOM-less .ps1 as ANSI/GBK and breaks on CJK.

param(
    [switch]$Uninstall,
    [switch]$List,
    [string]$TestFile
)
$ErrorActionPreference = 'Stop'

$root      = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # ...\kotonoha
$gameFile  = Join-Path $root 'kotonoha_Data\sharedassets0.assets'
$backupDir = Join-Path $PSScriptRoot '..\backup'
$workDir   = Join-Path $PSScriptRoot '..\work'
if (-not $TestFile) { $TestFile = Join-Path $workDir 'sharedassets0.test.assets' }

Write-Host "game   = $gameFile"
Write-Host "test   = $TestFile"
Write-Host "backup = $backupDir"

if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir | Out-Null }

if ($List) {
    Get-ChildItem $backupDir -Filter 'sharedassets0.before_assetfix_*.assets' |
        Sort-Object LastWriteTime -Descending |
        Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize
    return
}

if ($Uninstall) {
    $b = Get-ChildItem $backupDir -Filter 'sharedassets0.before_assetfix_*.assets' |
         Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $b) { throw 'no backup found, cannot rollback' }
    Copy-Item -LiteralPath $b.FullName -Destination $gameFile -Force
    $h = (Get-FileHash -LiteralPath $gameFile -Algorithm SHA256).Hash
    Write-Host "restored from $($b.Name)"
    Write-Host "game sha256 = $h  size = $((Get-Item $gameFile).Length)"
    return
}

if (-not (Test-Path $TestFile)) { throw "test file not found: $TestFile" }

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$bk = Join-Path $backupDir ("sharedassets0.before_assetfix_{0}.assets" -f $stamp)
Copy-Item -LiteralPath $gameFile -Destination $bk
Write-Host "backed up current file -> $(Split-Path -Leaf $bk)"

Copy-Item -LiteralPath $TestFile -Destination $gameFile -Force

$size = (Get-Item $gameFile).Length
$sha  = (Get-FileHash -LiteralPath $gameFile -Algorithm SHA256).Hash
$shaT = (Get-FileHash -LiteralPath $TestFile  -Algorithm SHA256).Hash
Write-Host "installed: size=$size"
Write-Host "game sha256 = $sha"
Write-Host "test sha256 = $shaT"
if ($sha -ne $shaT) { throw 'post-install hash mismatch' }
Write-Host 'OK'
