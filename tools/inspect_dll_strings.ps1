# Inspect Assembly-CSharp.dll string literals (ldstr) that still contain Japanese kana,
# and print the owning method for each, so we know whether it is user-visible code.
# READ-ONLY. ASCII-only on purpose (PowerShell 5.1 misreads BOM-less UTF-8 as ANSI).
param([string]$Root, [string]$Method, [switch]$All)
$ErrorActionPreference = 'Stop'
if (-not $Root) { $Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
Add-Type -Path (Join-Path $Root 'BepInEx\core\Mono.Cecil.dll')

$dll = Join-Path $Root 'kotonoha_Data\Managed\Assembly-CSharp.dll'
$resolver = New-Object Mono.Cecil.DefaultAssemblyResolver
$resolver.AddSearchDirectory((Join-Path $Root 'kotonoha_Data\Managed'))
$rp = New-Object Mono.Cecil.ReaderParameters
$rp.AssemblyResolver = $resolver
$asm = [Mono.Cecil.AssemblyDefinition]::ReadAssembly($dll, $rp)

# kana ranges as an ASCII regex pattern (also flags halfwidth katakana leftovers)
$kana = '[\u3040-\u309F\u30A0-\u30FF\uFF66-\uFF9D]'
$hits = 0

function Show-Str($ins, $s) {
    $esc = ($s.ToCharArray() | ForEach-Object { if ([int]$_ -lt 128) { [string]$_ } else { '\u{0:X4}' -f [int]$_ } }) -join ''
    Write-Host ("    IL_{0:x4} len={1} : {2}" -f $ins.Offset, $s.Length, $esc)
}

function Walk($t, $path) {
    foreach ($nt in $t.NestedTypes) { Walk $nt ($path + '/' + $nt.Name) }
    foreach ($m in $t.Methods) {
        if (-not $m.HasBody) { continue }
        $key = $path + '/' + $t.Name + '::' + $m.Name
        $dumpAll = ($Method -and $key -like ('*' + $Method + '*'))
        foreach ($ins in $m.Body.Instructions) {
            if ($ins.OpCode.Name -ne 'ldstr' -or -not $ins.Operand) { continue }
            $s = [string]$ins.Operand
            if ($dumpAll) { if ($All -or $s -match $kana) { $script:hits++; Show-Str $ins $s } ; continue }
            if ($s -notmatch $kana) { continue }
            $script:hits++
            Write-Host ("[{0} IL_{1:x4}] len={2}" -f $key, $ins.Offset, $s.Length)
            Show-Str $ins $s
        }
    }
}
foreach ($t in $asm.MainModule.Types) { Walk $t $t.Name }
Write-Host "TOTAL kana literals: $hits"
