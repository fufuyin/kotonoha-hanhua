# Compile decompiled sources with the Roslyn bundled inside dnSpy.
# Purpose: prove that a zero-logic-change rebuild of Assembly-CSharp.dll works.
# NOTE: keep this file ASCII-only. PowerShell 5.1 reads BOM-less UTF-8 as ANSI,
#       and non-ASCII bytes can turn into stray quote/backtick characters that break parsing.
param(
    [string]$SrcDir = '_hanhua\out\decomp\Assembly-CSharp',
    [string]$ManagedDir = 'kotonoha_Data\Managed',
    [string]$OutDll = '_hanhua\out\build\Assembly-CSharp.dll',
    [int]$MaxErrors = 30,
    [string]$RoslynBin = 'F:\Application\kks\[MODDING] Tools\dnSpy v6.1.5\bin'
)

$ErrorActionPreference = 'Stop'
Add-Type -Path (Join-Path $RoslynBin 'Microsoft.CodeAnalysis.dll')
Add-Type -Path (Join-Path $RoslynBin 'Microsoft.CodeAnalysis.CSharp.dll')

# References: every dll under Managed except the target itself.
# netstandard.dll facade is skipped to avoid duplicate type definitions vs mscorlib.
$skip = @('Assembly-CSharp.dll', 'netstandard.dll')
$refs = New-Object 'System.Collections.Generic.List[Microsoft.CodeAnalysis.MetadataReference]'
foreach ($dll in (Get-ChildItem $ManagedDir -Filter *.dll)) {
    if ($skip -contains $dll.Name) { continue }
    try {
        $refs.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile($dll.FullName))
    } catch {
        Write-Host "  [ref-skip] $($dll.Name): $($_.Exception.Message)"
    }
}
Write-Host "[refs] $($refs.Count)"

$parseOpts = New-Object Microsoft.CodeAnalysis.CSharp.CSharpParseOptions([Microsoft.CodeAnalysis.CSharp.LanguageVersion]::CSharp7_3)
$trees = New-Object 'System.Collections.Generic.List[Microsoft.CodeAnalysis.SyntaxTree]'
foreach ($f in (Get-ChildItem $SrcDir -Recurse -Filter *.cs)) {
    $text = [System.IO.File]::ReadAllText($f.FullName)
    $trees.Add([Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree]::ParseText($text, $parseOpts, $f.FullName))
}
Write-Host "[trees] $($trees.Count)"

$opts = New-Object Microsoft.CodeAnalysis.CSharp.CSharpCompilationOptions([Microsoft.CodeAnalysis.OutputKind]::DynamicallyLinkedLibrary)
$opts = $opts.WithAllowUnsafe($true).WithOptimizationLevel([Microsoft.CodeAnalysis.OptimizationLevel]::Debug).WithDeterministic($false)

$comp = [Microsoft.CodeAnalysis.CSharp.CSharpCompilation]::Create('Assembly-CSharp', $trees, $refs, $opts)
$diags = $comp.GetDiagnostics()
$errs = @($diags | Where-Object { $_.Severity -eq [Microsoft.CodeAnalysis.DiagnosticSeverity]::Error })
$warns = @($diags | Where-Object { $_.Severity -eq [Microsoft.CodeAnalysis.DiagnosticSeverity]::Warning })
Write-Host "[diag] errors=$($errs.Count) warnings=$($warns.Count)"

$errs | Group-Object { $_.Id } | Sort-Object Count -Descending | Select-Object -First 15 |
    ForEach-Object { Write-Host ("  {0,-10} x{1}" -f $_.Name, $_.Count) }
# per-error-ID samples to expose root causes of semantic errors
foreach ($id in @('CS1061', 'CS0104', 'CS0122', 'CS0012', 'CS0103', 'CS0116', 'CS0165', 'CS0030')) {
    $sample = @($errs | Where-Object { $_.Id -eq $id } | Select-Object -First 3)
    if ($sample.Count -gt 0) {
        Write-Host "--- $id samples"
        $sample | ForEach-Object { Write-Host ("   * " + $_.ToString()) }
    }
}
$errs | Select-Object -First $MaxErrors | ForEach-Object { Write-Host ("   - " + $_.ToString()) }

if ($errs.Count -eq 0) {
    $dir = Split-Path -Parent $OutDll
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $fs = [System.IO.File]::Create($OutDll)
    try { $res = $comp.Emit($fs) } finally { $fs.Close() }
    Write-Host "[emit] success=$($res.Success)"
    if (-not $res.Success) {
        @($res.Diagnostics | Where-Object { $_.Severity -eq [Microsoft.CodeAnalysis.DiagnosticSeverity]::Error }) |
            Select-Object -First 20 | ForEach-Object { Write-Host ("   ! " + $_.ToString()) }
    } else {
        Write-Host "[out] $OutDll $((Get-Item $OutDll).Length) bytes"
    }
}
