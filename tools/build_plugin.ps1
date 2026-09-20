# Compile the KotonohaCNFont BepInEx plugin with dnSpy's Roslyn (no .NET SDK on this box).
# ASCII-only on purpose: PowerShell 5.1 misreads BOM-less UTF-8 as ANSI.
param(
    [string]$Src = '_hanhua\plugin\KotonohaCNFont.cs',
    [string]$OutDll = 'BepInEx\plugins\KotonohaCNFont.dll',
    [string]$ManagedDir = 'kotonoha_Data\Managed',
    [string]$RoslynBin = 'F:\Application\kks\[MODDING] Tools\dnSpy v6.1.5\bin'
)
$ErrorActionPreference = 'Stop'
Add-Type -Path (Join-Path $RoslynBin 'Microsoft.CodeAnalysis.dll')
Add-Type -Path (Join-Path $RoslynBin 'Microsoft.CodeAnalysis.CSharp.dll')

$refFiles = @(
    'mscorlib.dll', 'System.dll', 'System.Core.dll', 'netstandard.dll',
    'UnityEngine.dll', 'UnityEngine.CoreModule.dll',
    'UnityEngine.TextRenderingModule.dll', 'UnityEngine.TextCoreModule.dll',
    'UnityEngine.ImageConversionModule.dll',
    'UnityEngine.AssetBundleModule.dll',
    'UnityEngine.UI.dll', 'Unity.TextMeshPro.dll'
)
$refs = New-Object 'System.Collections.Generic.List[Microsoft.CodeAnalysis.MetadataReference]'
foreach ($r in $refFiles) {
    $p = Join-Path $ManagedDir $r
    if (Test-Path $p) { $refs.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile((Resolve-Path $p).Path)) }
    else { Write-Host "  [missing ref] $r" }
}
# BepInEx core (already deployed)
foreach ($r in @('BepInEx\core\BepInEx.dll', 'BepInEx\core\0Harmony.dll')) {
    if (Test-Path $r) { $refs.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile((Resolve-Path $r).Path)) }
    else { Write-Host "  [missing ref] $r" }
}
Write-Host "[refs] $($refs.Count)"

$parseOpts = New-Object Microsoft.CodeAnalysis.CSharp.CSharpParseOptions([Microsoft.CodeAnalysis.CSharp.LanguageVersion]::CSharp7_3)
$text = [System.IO.File]::ReadAllText((Resolve-Path $Src).Path)
$tree = [Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree]::ParseText($text, $parseOpts, (Resolve-Path $Src).Path)
$trees = New-Object 'System.Collections.Generic.List[Microsoft.CodeAnalysis.SyntaxTree]'
$trees.Add($tree)

$opts = New-Object Microsoft.CodeAnalysis.CSharp.CSharpCompilationOptions([Microsoft.CodeAnalysis.OutputKind]::DynamicallyLinkedLibrary)
$opts = $opts.WithAllowUnsafe($true).WithOptimizationLevel([Microsoft.CodeAnalysis.OptimizationLevel]::Debug)

$comp = [Microsoft.CodeAnalysis.CSharp.CSharpCompilation]::Create('KotonohaCNFont', $trees, $refs, $opts)
$diags = $comp.GetDiagnostics()
$errs = @($diags | Where-Object { $_.Severity -eq [Microsoft.CodeAnalysis.DiagnosticSeverity]::Error })
Write-Host "[diag] errors=$($errs.Count)"
$errs | Select-Object -First 40 | ForEach-Object { Write-Host ("   - " + $_.ToString()) }

if ($errs.Count -eq 0) {
    $dir = Split-Path -Parent $OutDll
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $fs = [System.IO.File]::Create($OutDll)
    try { $res = $comp.Emit($fs) } finally { $fs.Close() }
    Write-Host "[emit] success=$($res.Success)"
    if ($res.Success) { Write-Host "[out] $OutDll $((Get-Item $OutDll).Length) bytes" }
}
