# Restore the game to the last user-verified STABLE state.
# Stable state = previous translator's patch + our verified fixes:
#   - resources.assets : BGM names translated, dialogue punctuation replaced, literal u3000 fixed
#   - Assembly-CSharp.dll : randomWord symbol patch (cross-font-safe symbols)
#   - level0 : font-array experiment REVERTED (original patch state)
#   - level4 / level121 : scene text translated to Chinese
# Everything else (sharedassets0.assets and the remaining level files) is unchanged
# from the previous translator's patch and can be re-copied from the patch folder if needed.
#
# ASCII-only on purpose: PowerShell 5.1 reads BOM-less UTF-8 as ANSI.
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$snap = Join-Path $root '_hanhua\backup\stable'
$items = @(
    @{ src = 'resources.assets';                dst = 'kotonoha_Data\resources.assets' },
    @{ src = 'Assembly-CSharp.dll';             dst = 'kotonoha_Data\Managed\Assembly-CSharp.dll' },
    @{ src = 'level0';                          dst = 'kotonoha_Data\level0' },
    @{ src = 'level4';                          dst = 'kotonoha_Data\level4' },
    @{ src = 'level121';                        dst = 'kotonoha_Data\level121' }
)
Write-Host "restoring stable snapshot from $snap"
foreach ($it in $items) {
    $s = Join-Path $snap $it.src
    $d = Join-Path $root $it.dst
    if (-not (Test-Path $s)) { Write-Warning "missing snapshot file: $s"; continue }
    Copy-Item $s $d -Force
    $len = (Get-Item $d).Length
    Write-Host ("  {0,-34} <- {1} bytes" -f $it.dst, $len)
}
Write-Host "[done] stable state restored."
