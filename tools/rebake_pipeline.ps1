# SimHei 重烤后的完整流水线：Unity 打包 -> 提取 SerializedFile -> 拼接进游戏资产 -> 独立校验 -> 可选安装
#   powershell -File rebake_pipeline.ps1              # 只产出 .test 并校验
#   powershell -File rebake_pipeline.ps1 -Install      # 校验 PASS 后安装
# ASCII-only on purpose（无 BOM 的 .ps1 被 PowerShell 5.1 按 GBK 读，中文会打断字符串）

param([switch]$Install)
$ErrorActionPreference = 'Stop'

$unity  = 'F:\Application\Unity\2019.1.13f1\Editor\Unity.exe'
$proj   = 'F:\Application\Unity'
$tools  = $PSScriptRoot
$root   = Split-Path -Parent (Split-Path -Parent $tools)          # ...\kotonoha
$work   = Join-Path $root '_hanhua\work'
$game   = Join-Path $root 'kotonoha_Data\sharedassets0.assets'
$bundle = Join-Path $proj 'bundles_raw\kotonoha_font.bundle'
$ser    = Join-Path $work 'our_simhei.serialized'
$test   = Join-Path $work 'sharedassets0.simhei.assets'

Write-Host "proj   = $proj"
Write-Host "bundle = $bundle"
Write-Host "game   = $game"

if (-not (Test-Path $unity)) { throw "unity not found: $unity" }

Write-Host '=== [1/5] Unity: BundleBuilder.Build ==='
$t0 = Get-Date
& $unity -batchmode -quit -projectPath $proj -executeMethod BundleBuilder.Build `
    -logFile (Join-Path $proj 'bundle_build.log')
# 坑：Unity 启动器会提前返回，真正的编辑器进程还在跑 -> 必须等 Unity.exe 全部退出
$waited = 0
while ((Get-Process Unity -ErrorAction SilentlyContinue) -and $waited -lt 1800) {
    Start-Sleep -Seconds 5; $waited += 5
}
Write-Host "waited ${waited}s for Unity to exit"
if (-not (Test-Path $bundle)) { throw "bundle not produced: $bundle (see bundle_build.log)" }
if ((Get-Item $bundle).LastWriteTime -lt $t0) { throw "bundle was NOT rebuilt (mtime older than this run)" }
Write-Host ("bundle size = {0}  mtime = {1}" -f (Get-Item $bundle).Length, (Get-Item $bundle).LastWriteTime)

Push-Location $tools
try {
    Write-Host '=== [2/5] extract SerializedFile ==='
    python .\bundle_serialized.py $bundle $ser
    if ($LASTEXITCODE -ne 0) { throw 'extract failed' }

    Write-Host '=== [3/5] splice into sharedassets0 (based on the CURRENT game file) ==='
    python .\splice_fonts.py --target $game --our $ser --out $test `
        --report (Join-Path $work 'simhei_splice_report.txt')
    if ($LASTEXITCODE -ne 0) { throw 'splice failed' }

    Write-Host '=== [4/5] independent verify ==='
    python .\verify_splice.py --orig $game --out $test --our $ser
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY FAILED - not installing' }

    Write-Host '=== [5/5] faceinfo check ==='
    python .\probe_faceinfo.py $test --pathid 0xbe

    if ($Install) {
        Write-Host '=== install ==='
        powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $tools 'install_assetfix.ps1') -TestFile $test
    } else {
        Write-Host "OK (test file ready, not installed): $test"
    }
} finally {
    Pop-Location
}
