# Restore the original Assembly-CSharp.dll, i.e. undo the "randomWord symbol substitution" hack.
# ASCII-only on purpose: PowerShell 5.1 misreads BOM-less UTF-8 as ANSI.
#
# Why this is safe now: the hack existed only because the old fonts could not render the
# original unreadable-language symbols. The new baked font covers 100% of them
# (check_randomword_coverage.py: "uncovered = 0"), namely:
#   fullwidth #  U+FF03, U+03A9 (Omega), U+2606 (star), U+FF20, U+FF06, U+FFE5,
#   U+2103, U+0414 (Cyrillic De), U+00B1, U+FF01
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File restore_randomword.ps1 -GameDir "...\kotonoha"
#   powershell -ExecutionPolicy Bypass -File restore_randomword.ps1 -GameDir "...\kotonoha" -Revert
param(
    [string]$GameDir = '',
    [switch]$Revert
)

$ErrorActionPreference = 'Stop'

function Find-GameDir([string]$hint) {
    $cands = New-Object System.Collections.Generic.List[string]
    if ($hint) { $cands.Add($hint) }
    $cands.Add((Get-Location).Path)
    foreach ($c in $cands) {
        if ($c -and (Test-Path (Join-Path $c 'kotonoha.exe'))) { return (Resolve-Path $c).Path }
    }
    return $null
}

if (-not $GameDir) { $GameDir = Find-GameDir '' }
if (-not $GameDir) { throw "Cannot find the game folder (kotonoha.exe). Pass -GameDir explicitly." }

$managed = Join-Path $GameDir 'kotonoha_Data\Managed'
$cur = Join-Path $managed 'Assembly-CSharp.dll'
$bak = Join-Path $managed 'Assembly-CSharp.dll.bak'
$pre = Join-Path $managed 'Assembly-CSharp.dll.before_restore'

if (-not (Test-Path $bak)) { throw "backup not found: $bak" }

if ($Revert) {
    if (-not (Test-Path $pre)) { throw "no pre-restore copy: $pre" }
    Copy-Item -LiteralPath $pre -Destination $cur -Force
    $ok = ((Get-FileHash -LiteralPath $cur).Hash -eq (Get-FileHash -LiteralPath $pre).Hash)
    Write-Host ("[revert] restored the patched dll from .before_restore exit; hash match = " + $ok)
    exit 0
}

if (-not (Test-Path $pre)) { Copy-Item -LiteralPath $cur -Destination $pre -Force; Write-Host ("[restore] saved current dll -> " + (Split-Path -Leaf $pre)) }

Copy-Item -LiteralPath $bak -Destination $cur -Force
$same = ((Get-FileHash -LiteralPath $cur).Hash -eq (Get-FileHash -LiteralPath $bak).Hash)
Write-Host ("[restore] Assembly-CSharp.dll now identical to .bak : " + $same)
if (-not $same) { throw "hash mismatch after restore" }
Write-Host "[restore] done. Note: this only affects the unreadable-language symbol set."
