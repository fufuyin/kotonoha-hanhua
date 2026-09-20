# Re-apply the minimal PoC (Chinese line into Story_00_00) on top of a clean resources.assets.
# ASCII-only on purpose: PowerShell 5.1 misreads BOM-less UTF-8 as ANSI.
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$py = 'python'
$env:PYTHONIOENCODING = 'utf-8'
Push-Location $root
try {
    & $py '_hanhua\tools\poc_patch_dialogue.py' --apply
} finally {
    Pop-Location
}
