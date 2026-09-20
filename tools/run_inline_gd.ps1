# Inline the GDhwGoJA atlas into resources.assets, verify, then install.
# ASCII-only on purpose (PowerShell 5.1 misreads BOM-less UTF-8 as ANSI).
$ErrorActionPreference = 'Stop'
$tools = $PSScriptRoot
$root  = Split-Path -Parent (Split-Path -Parent $tools)      # ...\kotonoha
$g     = Join-Path $root 'kotonoha_Data'
$w     = Join-Path $root '_hanhua\work'
$b     = Join-Path $root '_hanhua\backup'
Set-Location $tools

$log = Join-Path $w 'inline_gd.log'
python .\inline_gd_atlas.py --res (Join-Path $g 'resources.assets') `
    --out (Join-Path $w 'resources.inline.assets') *> $log
$code = $LASTEXITCODE
Get-Content $log -Tail 9
if ($code -ne 0) { Write-Host "VERIFY FAILED (exit=$code) - nothing installed"; exit 1 }

Copy-Item (Join-Path $g 'resources.assets') (Join-Path $b 'resources.assets.before_inline') -Force
Copy-Item (Join-Path $w 'resources.inline.assets') (Join-Path $g 'resources.assets') -Force
$sz = (Get-Item (Join-Path $g 'resources.assets')).Length
$h1 = (Get-FileHash (Join-Path $g 'resources.assets') -Algorithm SHA256).Hash
$h2 = (Get-FileHash (Join-Path $w 'resources.inline.assets') -Algorithm SHA256).Hash
Write-Host ("installed size={0} hashmatch={1}" -f $sz, ($h1 -eq $h2))
