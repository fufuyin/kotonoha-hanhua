# Patch leftover Japanese string literals in Assembly-CSharp.dll using Mono.Cecil (ldstr),
# scoped per (type, method) so unrelated literals can never be touched.
#
# Same mechanism the earlier verified randomWord patch used.
# ASCII-only on purpose: PowerShell 5.1 reads BOM-less UTF-8 as ANSI.
# The old/new strings live in dll_fix_map.json (read with -Encoding UTF8).
#
# Usage:
#   powershell -File patch_dll_literals.ps1 -Root <game root>              # dry run
#   powershell -File patch_dll_literals.ps1 -Root <game root> -Apply
param(
    [string]$Root,
    [string]$Map,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
if (-not $Root) { $Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
if (-not $Map) { $Map = Join-Path $PSScriptRoot 'dll_fix_map.json' }
Add-Type -Path (Join-Path $Root 'BepInEx\core\Mono.Cecil.dll')

$dll = Join-Path $Root 'kotonoha_Data\Managed\Assembly-CSharp.dll'
$plan = Get-Content -LiteralPath $Map -Encoding UTF8 -Raw | ConvertFrom-Json
Write-Host ("[map] entries: " + $plan.Count)

function Esc([string]$s) {
    ($s.ToCharArray() | ForEach-Object { if ([int]$_ -lt 128) { [string]$_ } else { '\u{0:X4}' -f [int]$_ } }) -join ''
}

$resolver = New-Object Mono.Cecil.DefaultAssemblyResolver
$resolver.AddSearchDirectory((Join-Path $Root 'kotonoha_Data\Managed'))
$rp = New-Object Mono.Cecil.ReaderParameters
$rp.AssemblyResolver = $resolver
$asm = [Mono.Cecil.AssemblyDefinition]::ReadAssembly($dll, $rp)

function Walk($t) {
    foreach ($nt in $t.NestedTypes) { Walk $nt }
    foreach ($m in $t.Methods) {
        if (-not $m.HasBody) { continue }
        foreach ($ins in $m.Body.Instructions) {
            if ($ins.OpCode.Name -ne 'ldstr' -or -not $ins.Operand) { continue }
            $s = [string]$ins.Operand
            foreach ($e in $plan) {
                if ($e.type -ne $t.Name -or $e.method -ne $m.Name) { continue }
                if ($s -ne $e.old) { continue }
                $script:matched++
                Write-Host ("  MATCH {0}::{1} IL_{2:x4}" -f $e.type, $e.method, $ins.Offset)
                Write-Host ("     old: " + (Esc $e.old))
                Write-Host ("     new: " + (Esc $e.new))
                if ($Apply) { $ins.Operand = $e.new }
                $script:done++
            }
        }
    }
}

$matched = 0
$done = 0
foreach ($t in $asm.MainModule.Types) { Walk $t }
Write-Host ("[result] matched=$matched applied=$done")

if (-not $Apply) {
    Write-Host "[dry-run] nothing written; add -Apply"
    exit 0
}
if ($matched -eq 0) { Write-Host "[abort] nothing matched"; exit 2 }

$backup = $dll + '.before_names'
if (-not (Test-Path $backup)) {
    Copy-Item -LiteralPath $dll -Destination $backup -Force
    Write-Host ("[backup] -> " + (Split-Path -Leaf $backup))
} else { Write-Host ("[backup] kept existing " + (Split-Path -Leaf $backup)) }

$sizeBefore = (Get-Item -LiteralPath $dll).Length
# Cecil's read stream stays open until Dispose, so writing to the SAME path fails with
# "used by another process". Write to a temp file first, then replace.
$tmpOut = $dll + '.cecil_tmp'
if (Test-Path $tmpOut) { Remove-Item -LiteralPath $tmpOut -Force }
$asm.Write($tmpOut)
$asm.Dispose()
Copy-Item -LiteralPath $tmpOut -Destination $dll -Force
Remove-Item -LiteralPath $tmpOut -Force
$sizeAfter = (Get-Item -LiteralPath $dll).Length
Write-Host ("[write] size {0} -> {1}" -f $sizeBefore, $sizeAfter)

# verify: reload and check every mapping is applied (or the literal is gone)
$asm2 = [Mono.Cecil.AssemblyDefinition]::ReadAssembly($dll, $rp)
$left = 0
function Walk2($t) {
    foreach ($nt in $t.NestedTypes) { Walk2 $nt }
    foreach ($m in $t.Methods) {
        if (-not $m.HasBody) { continue }
        foreach ($ins in $m.Body.Instructions) {
            if ($ins.OpCode.Name -ne 'ldstr' -or -not $ins.Operand) { continue }
            $s = [string]$ins.Operand
            foreach ($e in $plan) { if ($e.type -eq $t.Name -and $e.method -eq $m.Name -and $s -eq $e.old) { $script:left++ } }
        }
    }
}
$left = 0
foreach ($t in $asm2.MainModule.Types) { Walk2 $t }
Write-Host ("[verify] remaining old literals: " + $left)
$asm2.Dispose()
