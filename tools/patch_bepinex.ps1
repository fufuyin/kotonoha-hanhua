# Surgical IL patch for BepInEx 5.4.23 preloader.
# Problem: BepInEx's own Harmony-based runtime fixes crash on this game's stripped Mono
#          (NullReferenceException in HarmonyX StackTraceFixes.OnILChainRefresh), and the
#          fatal calls abort the preloader before the Chainloader is ever patched in.
# Fix:     NOP the three fatal Harmony-based calls. Our own plugin does not use Harmony.
# Targets (BepInEx.Preloader.dll):
#   PreloaderRunner::PreloaderMain  -> XTermFix::Apply, ConsoleSetOutFix::Apply
#   Preloader::Run                  -> HarmonyInteropFix::Apply
# ASCII-only on purpose: PowerShell 5.1 misreads BOM-less UTF-8 as ANSI.
param(
    [string]$Root,
    [switch]$VerifyOnly
)
$ErrorActionPreference = 'Stop'
# Derive the game root from this script's location (<root>\_hanhua\tools\patch_bepinex.ps1)
# so that no non-ASCII path literal appears in this file (PS 5.1 reads BOM-less UTF-8 as ANSI).
if (-not $Root) { $Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
$cecil = Join-Path $Root 'BepInEx\core\Mono.Cecil.dll'
$target = Join-Path $Root 'BepInEx\core\BepInEx.Preloader.dll'
Add-Type -Path $cecil

$targets = @(
    'System.Void BepInEx.Preloader.RuntimeFixes.XTermFix::Apply()',
    'System.Void BepInEx.Preloader.RuntimeFixes.ConsoleSetOutFix::Apply()',
    'System.Void BepInEx.Preloader.RuntimeFixes.HarmonyInteropFix::Apply()'
)

function Get-AllMethods([Mono.Cecil.TypeDefinition]$t) {
    foreach ($m in $t.Methods) { $m }
    foreach ($n in $t.NestedTypes) { Get-AllMethods $n }
}

$asm = [Mono.Cecil.AssemblyDefinition]::ReadAssembly($target)
$patched = 0
$remaining = @()
foreach ($t in $asm.MainModule.Types) {
    foreach ($m in (Get-AllMethods $t)) {
        if (-not $m.HasBody) { continue }
        foreach ($ins in $m.Body.Instructions) {
            if (-not $ins.Operand) { continue }
            $op = "$($ins.Operand)"
            if ($targets -contains $op) {
                if ($VerifyOnly) {
                    $remaining += "  $($t.FullName)::$($m.Name) IL_$($ins.Offset.ToString('x4')) -> $op"
                } else {
                    $ins.OpCode = [Mono.Cecil.Cil.OpCodes]::Nop
                    $ins.Operand = $null
                    $patched++
                    Write-Host "  PATCHED $($t.FullName)::$($m.Name) IL_$($ins.Offset.ToString('x4')) -> $op"
                }
            }
        }
    }
}

if ($VerifyOnly) {
    if ($remaining.Count -eq 0) { Write-Host '[verify] OK - no Harmony runtime-fix calls remain' }
    else { Write-Host "[verify] STILL PRESENT ($($remaining.Count)):"; $remaining | ForEach-Object { Write-Host $_ } }
    exit 0
}

if ($patched -eq 0) { Write-Host '[patch] nothing matched - already patched?'; exit 0 }

$backup = "$target.bak"
if (-not (Test-Path $backup)) { Copy-Item $target $backup -Force; Write-Host "  backup -> $backup" }
$tmp = "$target.patched"
$asm.Write($tmp)
$asm.Dispose()
Copy-Item $tmp $target -Force
Remove-Item $tmp -Force
Write-Host "[patch] done, $patched call(s) neutralised -> $target"
