# Surgical IL patch: replace the 12 string literals of NobelUIScript.randomWord
# so that the "unreadable foreign language" effect renders with glyphs the game's
# Chinese font (Gyate) actually has, instead of showing missing-glyph boxes.
#
# Original  : ？ Ω ＃ ☆ ％ ＠ ＆ ￥ ℃ Д ± ！
# Gyate has : only ！
# Replacement (all verified present in Gyate's character table):
#             。 、 ！ 「 」 『 【 〔 〖 々 〈 〉
#
# Same array length, no metadata growth -> very low risk.
# ASCII-only on purpose: PowerShell 5.1 reads BOM-less UTF-8 as ANSI.
param(
    [string]$Root,
    [switch]$VerifyOnly
)
$ErrorActionPreference = 'Stop'
if (-not $Root) { $Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
Add-Type -Path (Join-Path $Root 'BepInEx\core\Mono.Cecil.dll')

$dll = Join-Path $Root 'kotonoha_Data\Managed\Assembly-CSharp.dll'
$old = @([char]0xFF1F, [char]0x03A9, [char]0xFF03, [char]0x2606, [char]0xFF05,
         [char]0xFF20, [char]0xFF06, [char]0xFFE5, [char]0x2103, [char]0x0414,
         [char]0x00B1, [char]0xFF01) | ForEach-Object { [string]$_ }
$new = @([char]0x3002, [char]0x3001, [char]0xFF01, [char]0x300C, [char]0x300D,
         [char]0x300E, [char]0x3010, [char]0x3014, [char]0x3016, [char]0x3005,
         [char]0x3008, [char]0x3009) | ForEach-Object { [string]$_ }

function Get-Methods($t) {
    foreach ($m in $t.Methods) { $m }
    foreach ($n in $t.NestedTypes) { Get-Methods $n }
}

# Stage 2: U+3016 was in Gyate only -> not in the 5-font intersection -> showed boxes.
# Replace it with U+300A 《 which IS present in all five fonts.
$old += [string][char]0x3016
$new += [string][char]0x300A

# Only these two methods may be touched. The same symbol literals also appear in
# MenuUI_Option/GalleryScript ('％' = volume percent) and EnemyHPScript ('？' = unknown HP),
# which are normal functionality and must NOT be rewritten.
$allowed = @('NobelUIScript::.ctor', 'NobelUIScript::changeSeacretWord')

# Cecil needs to resolve referenced assemblies (UnityEngine.*, mscorlib...) to write the file.
$resolver = New-Object Mono.Cecil.DefaultAssemblyResolver
$resolver.AddSearchDirectory((Join-Path $Root 'kotonoha_Data\Managed'))
$rp = New-Object Mono.Cecil.ReaderParameters
$rp.AssemblyResolver = $resolver
$asm = [Mono.Cecil.AssemblyDefinition]::ReadAssembly($dll, $rp)
$found = 0
$verify = @()
foreach ($t in $asm.MainModule.Types) {
    foreach ($m in (Get-Methods $t)) {
        if (-not $m.HasBody) { continue }
        $key = "$($t.Name)::$($m.Name)"
        if ($allowed -notcontains $key) { continue }
        foreach ($ins in $m.Body.Instructions) {
            if ($ins.OpCode.Name -ne 'ldstr' -or -not $ins.Operand) { continue }
            $s = [string]$ins.Operand
            if ($s -eq [string][char]0xFF03) { $ins.Operand = [string][char]0x3005; if (-not $VerifyOnly) { $found++; Write-Host "  REPLACED $key IL_$($ins.Offset.ToString('x4'))  U+FF03 -> U+3005 (censored marker)" }; if ($VerifyOnly) { $verify += "  $key IL_$($ins.Offset.ToString('x4')) still U+FF03" }; continue }
            $idx = [Array]::IndexOf($old, $s)
            if ($idx -lt 0) { continue }
            if ($VerifyOnly) {
                $verify += "  $key IL_$($ins.Offset.ToString('x4')) still '$s'"
            } else {
                $ins.Operand = [string]$new[$idx]
                $found++
                Write-Host "  REPLACED $key IL_$($ins.Offset.ToString('x4'))  U+$('{0:X4}' -f [int][char]$old[$idx]) -> U+$('{0:X4}' -f [int][char]$new[$idx])"
            }
        }
    }
}
if ($VerifyOnly) {
    if ($verify.Count -eq 0) { Write-Host '[verify] OK - no original randomWord literals remain' }
    else { Write-Host "[verify] STILL PRESENT ($($verify.Count)):"; $verify | ForEach-Object { Write-Host $_ } }
    exit 0
}
if ($found -eq 0) { Write-Host '[patch] no matching literals found'; exit 0 }

$backup = "$dll.bak"
if (-not (Test-Path $backup)) { Copy-Item $dll $backup -Force; Write-Host "  backup -> $backup" }
$tmp = "$dll.patched"
$asm.Write($tmp)
$asm.Dispose()
Copy-Item $tmp $dll -Force
Remove-Item $tmp -Force
Write-Host "[patch] replaced $found literals -> $dll"
