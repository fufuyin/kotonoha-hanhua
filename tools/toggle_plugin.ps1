# Toggle the BepInEx font plugin (A/B test only).
#   powershell -File toggle_plugin.ps1 -Status
#   powershell -File toggle_plugin.ps1 -Off
#   powershell -File toggle_plugin.ps1 -On
# ASCII-only on purpose: PowerShell 5.1 reads BOM-less .ps1 as ANSI/GBK and breaks on CJK.

param([switch]$Status, [switch]$Off, [switch]$On)
$ErrorActionPreference = 'Stop'

$root    = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$plugDir = Join-Path $root 'BepInEx\plugins'
$dll     = Join-Path $plugDir 'KotonohaCNFont.dll'
$dis     = Join-Path $plugDir 'KotonohaCNFont.dll.disabled'

function Show-Status {
    if (Test-Path $dll)     { Write-Host 'status: ENABLED' }
    elseif (Test-Path $dis) { Write-Host 'status: DISABLED' }
    else                    { Write-Host 'status: plugin not found' }
    Write-Host "plugin dir = $plugDir"
    Get-ChildItem $plugDir -Filter 'KotonohaCNFont*' -ErrorAction SilentlyContinue |
        Select-Object Name, Length | Format-Table -AutoSize
}

if (-not ($Off -or $On)) { Show-Status; return }

if ($Off) {
    if (-not (Test-Path $dll)) { Write-Host 'already disabled or missing'; Show-Status; return }
    if (Test-Path $dis) { Remove-Item -LiteralPath $dis -Force }
    Rename-Item -LiteralPath $dll -NewName 'KotonohaCNFont.dll.disabled'
    Write-Host 'plugin disabled'
}
if ($On) {
    if (-not (Test-Path $dis)) { Write-Host 'already enabled or missing'; Show-Status; return }
    if (Test-Path $dll) { Remove-Item -LiteralPath $dll -Force }
    Rename-Item -LiteralPath $dis -NewName 'KotonohaCNFont.dll'
    Write-Host 'plugin enabled'
}
Show-Status
