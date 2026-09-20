#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
打包"一键汉化补丁"（外机试验用）。

内容 =
  ① 原补丁 alpha1.2 的全部文件（它本身就是 kotonoha_Data 的内容）
  ② 覆盖上我们改过的文件（字体/文本层）：sharedassets0.assets、resources.assets、
     Managed\Assembly-CSharp.dll、level0、level4、level121
  ③ BepInEx 运行时 + 字体插件 + 字体 bundle（当前其它 4 个字体仍由插件覆盖）
  ④ manifest.tsv（逐文件 sha256）+ install.ps1 + install.bat + rollback 支持 + 中文说明

用法: python build_dist.py [--out <dir>]
"""
import os, sys, shutil, hashlib, argparse, datetime

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

LIVE = r'F:\Steam\steamapps\common\琴葉姉妹とライサント島の伝説\kotonoha'
PATCH = r'D:\桌面\补丁alpha1.2-放在kotonoha_Data下'
DEFAULT_OUT = os.path.join(LIVE, '_hanhua', 'dist_first_test')

OVERLAY = ['kotonoha_Data\\sharedassets0.assets',
           'kotonoha_Data\\resources.assets',
           'kotonoha_Data\\Managed\\Assembly-CSharp.dll',
           'kotonoha_Data\\level0',
           'kotonoha_Data\\level4',
           'kotonoha_Data\\level121']

BEPINEX_TOP = ['winhttp.dll', 'doorstop_config.ini']
BEPINEX_DIRS = ['BepInEx\\core', 'BepInEx\\plugins', 'BepInEx\\config']
SKIP_NAMES = {'LogOutput.log', 'LogOutput.log.1'}
SKIP_DIRS = {'cache'}


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()


def copy_file(src, dst, files, base):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    rel = os.path.relpath(dst, base).replace('/', '\\')
    files[rel] = os.path.getsize(dst)


def collect_dir(src_dir, dst_dir, files, base):
    for dp, dns, fns in os.walk(src_dir):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if fn in SKIP_NAMES:
                continue
            s = os.path.join(dp, fn)
            rel = os.path.relpath(s, src_dir)
            copy_file(s, os.path.join(dst_dir, rel), files, base)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=DEFAULT_OUT)
    a = ap.parse_args()
    out = a.out
    if os.path.exists(out):
        print(f'清空旧目录 {out}')
        shutil.rmtree(out)
    os.makedirs(out)
    files = {}

    # ① 原补丁全部文件 -> kotonoha_Data\
    print(f'[1] 复制原补丁 {PATCH}')
    n0 = 0
    for dp, dns, fns in os.walk(PATCH):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            s = os.path.join(dp, fn)
            rel = os.path.relpath(s, PATCH)
            dst = os.path.join(out, 'kotonoha_Data', rel)
            copy_file(s, dst, files, out)
            n0 += 1
    print(f'    {n0} 个文件')

    # ② 覆盖我们改过的文件
    print('[2] 覆盖我们改过的文件')
    for rel in OVERLAY:
        src = os.path.join(LIVE, rel)
        if not os.path.exists(src):
            print(f'    !! 缺少 {rel}'); continue
        dst = os.path.join(out, rel)
        old = files.get(rel)
        copy_file(src, dst, files, out)
        print(f'    {rel}  {os.path.getsize(src)} 字节' + (f'  (替换补丁版 {old})' if old else ''))

    # ③ BepInEx
    print('[3] 复制 BepInEx')
    for rel in BEPINEX_TOP:
        src = os.path.join(LIVE, rel)
        if os.path.exists(src):
            copy_file(src, os.path.join(out, rel), files, out)
            print(f'    {rel}')
        else:
            print(f'    !! 缺少 {rel}')
    for d in BEPINEX_DIRS:
        src = os.path.join(LIVE, d)
        if os.path.isdir(src):
            collect_dir(src, os.path.join(out, d), files, out)
            print(f'    {d}\\')
        else:
            print(f'    !! 缺少目录 {d}')

    # ④ manifest
    rows = []
    for rel, size in sorted(files.items()):
        h = sha256(os.path.join(out, rel))
        rows.append(f'{rel}\t{size}\t{h}')
    with open(os.path.join(out, 'manifest.tsv'), 'w', encoding='utf-8') as f:
        f.write('path\tsize\tsha256\n')
        f.write('\n'.join(rows) + '\n')

    # ⑤ 安装脚本（纯 ASCII，避免 PowerShell 5.1 按 GBK 读 .ps1 出错）
    install = r'''param([string]$GameRoot)
$ErrorActionPreference = 'Stop'
$pkg = $PSScriptRoot
if (-not $GameRoot) {
    foreach ($c in @($pwd.Path, (Split-Path -Parent $pwd.Path))) {
        if (Test-Path (Join-Path $c 'kotonoha_Data\sharedassets0.assets')) { $GameRoot = $c; break }
    }
}
if (-not $GameRoot) { $GameRoot = Read-Host 'Enter the game folder (the one that contains kotonoha_Data)' }
if (-not (Test-Path (Join-Path $GameRoot 'kotonoha_Data\sharedassets0.assets'))) {
    throw "not a valid game folder (kotonoha_Data\sharedassets0.assets not found): $GameRoot"
}
$rows = Import-Csv (Join-Path $pkg 'manifest.tsv') -Delimiter "`t"
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$bk = Join-Path $GameRoot ("_cn_backup_" + $stamp)
Write-Host "game   = $GameRoot"
Write-Host "backup = $bk"
New-Item -ItemType Directory -Force -Path $bk | Out-Null
$added = New-Object System.Collections.Generic.List[string]
foreach ($r in $rows) {
    $src = Join-Path $pkg $r.path
    $dst = Join-Path $GameRoot $r.path
    if (Test-Path -LiteralPath $dst) {
        $bkf = Join-Path $bk $r.path
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $bkf) | Out-Null
        Copy-Item -LiteralPath $dst -Destination $bkf -Force
    } else {
        $added.Add($r.path)
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
    Copy-Item -LiteralPath $src -Destination $dst -Force
}
Set-Content -Path (Join-Path $bk 'added_files.txt') -Value $added -Encoding ASCII
$bad = 0
foreach ($r in $rows) {
    $h = (Get-FileHash -LiteralPath (Join-Path $GameRoot $r.path) -Algorithm SHA256).Hash
    if ($h -ne $r.sha256) { Write-Host ("MISMATCH " + $r.path); $bad++ }
}
Write-Host ("verified: " + ($rows.Count - $bad) + "/" + $rows.Count + " files")
$rollback = @'
$here = $PSScriptRoot
$game = Split-Path -Parent $here
Get-ChildItem -LiteralPath $here -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($here.Length + 1)
    if ($rel -eq 'added_files.txt' -or $rel -eq 'rollback.ps1') { return }
    $dst = Join-Path $game $rel
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
}
$addedFile = Join-Path $here 'added_files.txt'
if (Test-Path $addedFile) {
    Get-Content $addedFile | Where-Object { $_ } | ForEach-Object {
        $p = Join-Path $game $_
        if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force }
    }
}
Write-Host 'rollback done'
'@
Set-Content -Path (Join-Path $bk 'rollback.ps1') -Value $rollback -Encoding ASCII
if ($bad -gt 0) { throw "verification failed for $bad file(s)" }
Write-Host ''
Write-Host 'DONE - launch the game to test.'
Write-Host ("Rollback: powershell -ExecutionPolicy Bypass -File `"" + (Join-Path $bk 'rollback.ps1') + "`"")
'''
    with open(os.path.join(out, 'install.ps1'), 'w', encoding='ascii') as f:
        f.write(install)
    bat = '@echo off\r\npowershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"\r\npause\r\n'
    with open(os.path.join(out, 'install.bat'), 'w', encoding='ascii') as f:
        f.write(bat)

    # ⑥ 中文说明
    readme = f'''琴葉姉妹とライサント島の伝説 —— 简体中文补丁（外机试验版）
生成时间：{datetime.datetime.now():%Y-%m-%d %H:%M}

【怎么装】
1. 把整个文件夹复制到任意位置
2. 双击 install.bat（或在文件夹里执行 powershell -ExecutionPolicy Bypass -File install.ps1）
   - 脚本会自动找游戏目录；找不到时会提示你输入（就是包含 kotonoha_Data 的那个目录）
   - 装完会自动逐个校验文件哈希，显示 verified: N/N files 才算成功
3. 启动游戏

【为什么要带 BepInEx】
字体资产目前只做了主字体（对话/正文），菜单等另外 4 个字体仍由 BepInEx 插件在运行时覆盖。
后续版本会做成纯静态（不带 BepInEx）。

【怎么卸载】
安装时会在游戏目录生成 _cn_backup_<时间戳>\\，运行里面的 rollback.ps1 即可完整回滚
（包括删除安装时新增、原来不存在的文件）。

【已知问题】
- 菜单里「敌人」「恢复默认设置」会折成两行；退出确认弹窗文字有重叠
- 金币描边偏重（正在调整）

【校验】
manifest.tsv 里是每个文件的 sha256，安装脚本会自动核对。
'''
    with open(os.path.join(out, '安装说明.txt'), 'w', encoding='utf-8') as f:
        f.write(readme)

    total = sum(files.values())
    print(f'\n[out] {out}')
    print(f'      文件数 {len(files)}，总大小 {total / 1024 / 1024:.1f} MB')
    for k in ('kotonoha_Data\\sharedassets0.assets', 'BepInEx\\plugins\\kotonoha_font.bundle',
              'BepInEx\\plugins\\KotonohaCNFont.dll', 'kotonoha_Data\\resources.assets'):
        if k in files:
            print(f'      {k}  {files[k]} 字节  sha256={sha256(os.path.join(out, k))[:16]}')


if __name__ == '__main__':
    main()
