#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
清理 _hanhua 下的冗余大文件（保留：原版参考基线、最近一次回滚点、当前产物、文档、工具）。

原则：
  * 只删"可从现存文件再生成/已被现状取代"的中间产物
  * 保留 _hanhua\backup\original\*（原版基线）、最新一个 sharedassets0.before_assetfix_*、
    resources.assets.before_inline（最近一次回滚点）、resources.assets.orig、风格 bundle 备份
  * 默认 dry-run，加 --apply 才真删

用法: python cleanup_hanhua.py [--apply]
"""
import os, sys, glob, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # ...\_hanhua
WORK = os.path.join(ROOT, 'work')
BACK = os.path.join(ROOT, 'backup')

KEEP_WORK = {'our_simhei.serialized', 'sharedassets0.assets', 'splice_report.txt',
             'simhei_splice_report.txt', 'probe_report.txt'}


def mb(n):
    return f'{n / 1024 / 1024:.1f} MB'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    targets = []

    # 1) work 目录：除保留清单外的文件/目录
    for e in sorted(os.listdir(WORK)):
        p = os.path.join(WORK, e)
        if e in KEEP_WORK:
            continue
        if e in ('payloads',) or os.path.isfile(p):
            targets.append(p)

    # 2) 过期的老回滚点：只保留最新一个 sharedassets0.before_assetfix_*
    old = sorted(glob.glob(os.path.join(BACK, 'sharedassets0.before_assetfix_*.assets')),
                 key=os.path.getmtime)
    targets += old[:-1] if len(old) > 1 else []

    # 3) 已被现状取代的备份（注意：resources.assets.before_gd 保留——它含文本层修正，不是纯冗余）
    for name in ('resources.assets.before_gd',):
        p = os.path.join(BACK, name)
        if os.path.exists(p):
            print(f'  [keep] {name}（含文本层修正，保留）')

    # 3b) 删 .resS 备份前的前置校验：live .resS 必须与备份哈希一致
    ress_back = os.path.join(BACK, 'resources.assets.resS.before_gd')
    ress_live = os.path.join(os.path.dirname(ROOT), 'kotonoha_Data', 'resources.assets.resS')
    if os.path.exists(ress_back) and os.path.exists(ress_live):
        import hashlib
        def h(p):
            m = hashlib.sha256()
            with open(p, 'rb') as f:
                for b in iter(lambda: f.read(1 << 20), b''):
                    m.update(b)
            return m.hexdigest()
        hb, hl = h(ress_back), h(ress_live)
        print(f'  [guard] .resS live/backup 哈希一致 = {hb == hl}')
        if hb == hl:
            targets.append(ress_back)
        else:
            print('  [guard] !! 不一致 -> 保留备份，不删')

    total = 0
    print(f'{"DELETE" if a.apply else "DRY-RUN"} —— 计划删除 {len(targets)} 项：')
    for p in targets:
        rel = os.path.relpath(p, ROOT)
        if os.path.isdir(p):
            sz = sum(os.path.getsize(os.path.join(dp, f)) for dp, dn, fn in os.walk(p) for f in fn)
            kind = 'dir '
        else:
            sz = os.path.getsize(p)
            kind = 'file'
        total += sz
        print(f'  [{kind}] {rel}  {mb(sz)}')
        if a.apply:
            if os.path.isdir(p):
                import shutil
                shutil.rmtree(p)
            else:
                os.remove(p)
    print(f'合计 {"已释放" if a.apply else "将释放"}: {mb(total)}')

    print('\n保留（关键项）:')
    for p in sorted(glob.glob(os.path.join(BACK, 'original', '*'))):
        print(f'  keep {os.path.relpath(p, ROOT)}  {mb(os.path.getsize(p))}')
    for p in sorted(glob.glob(os.path.join(BACK, '*.bundle'))):
        print(f'  keep {os.path.relpath(p, ROOT)}  {mb(os.path.getsize(p))}')
    for name in ('resources.assets.orig', 'resources.assets.before_inline'):
        p = os.path.join(BACK, name)
        if os.path.exists(p):
            print(f'  keep {name}  {mb(os.path.getsize(p))}')
    newest = sorted(glob.glob(os.path.join(BACK, 'sharedassets0.before_assetfix_*.assets')),
                    key=os.path.getmtime)
    if newest:
        print(f'  keep 最新回滚点 {os.path.basename(newest[-1])}  {mb(os.path.getsize(newest[-1]))}')
    for name in sorted(KEEP_WORK):
        p = os.path.join(WORK, name)
        if os.path.exists(p):
            print(f'  keep work\\{name}  {mb(os.path.getsize(p))}')


if __name__ == '__main__':
    main()
