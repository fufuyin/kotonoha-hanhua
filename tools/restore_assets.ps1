# Restore the original resources.assets from the PoC backup.
# ASCII-only on purpose: PowerShell 5.1 misreads BOM-less UTF-8 as ANSI.
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$backup = Join-Path $root '_hanhua\backup\resources.assets.orig'
$target = Join-Path $root 'kotonoha_Data\resources.assets'
if (-not (Test-Path $backup)) { Write-Error "backup not found: $backup"; exit 1 }
Copy-Item $backup $target -Force
$len = (Get-Item $target).Length
Write-Host "[restore] resources.assets restored from backup ($len bytes)"
