#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成「重烤字体时的推荐字符集」：
  = 译文/UI/场景/DLL 用到的全部字符
  ∪ 原版五个字体已烘焙的字符（保留残留日文可渲染）
  ∪ ASCII 与常用标点/全角形式
输出到 _hanhua/out/bake_charset.txt，并给出按图集容量估算的分布建议。

用法: python make_bake_charset.py <原始游戏目录> <补丁目录>
"""
import sys, os, glob, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
import parse_tmp_font as PTF

EXTRA = set()
for a in range(0x20, 0x7F):                       # ASCII 可见字符
    EXTRA.add(a)
for a in range(0xFF01, 0xFF5F):                   # 全角 ASCII
    EXTRA.add(a)
for a in (0x3000, 0x3001, 0x3002, 0x300C, 0x300D, 0x300E, 0x300F, 0x3010, 0x3011,
          0x301C, 0x301D, 0x301F, 0x30FB, 0x30FC, 0x2015, 0x2018, 0x2019, 0x201C,
          0x201D, 0x2026, 0x2010, 0x00B7, 0x00A5, 0x203B, 0x3013, 0x3231, 0x3232,
          0x3239, 0x32A4, 0x32A5, 0x32A6, 0x32A7, 0x32A8, 0x33A1, 0x337B, 0x33CD):
    EXTRA.add(a)


def font_sets(path):
    out = set()
    if not os.path.exists(path):
        return out
    f = UnityFile(path, verbose=False)
    for o in f.objects:
        if o['classID'] != 114 or o['byteSize'] < 100000:
            continue
        raw = f.buf[o['abs']:o['abs'] + o['byteSize']]
        for _, vals in PTF.detect_runs(raw, 64):
            out |= set(vals)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('orig_dir')
    ap.add_argument('patch_dir')
    a = ap.parse_args()
    need = set(EXTRA)
    need |= font_sets(os.path.join(a.orig_dir, 'resources.assets'))
    need |= font_sets(os.path.join(a.orig_dir, 'sharedassets0.assets'))
    tp = '_hanhua/out/patch_texts'
    for p in glob.glob(os.path.join(tp, '*.txt')):
        need |= {ord(c) for c in open(p, encoding='utf-8', errors='ignore').read()}
    # UI / 场景 / DLL 的字符统一从补丁资源里扫（放宽到 4 连串以降噪）
    import check_coverage_all as C
    for name in ('resources.assets', 'sharedassets0.assets'):
        p = os.path.join(a.patch_dir, name)
        if os.path.exists(p):
            need |= {ord(c) for c in C.scan_asset_strings(p)}
    lv = [os.path.join(a.patch_dir, f) for f in os.listdir(a.patch_dir)
          if f.startswith('level') and '.' not in f]
    for p in sorted(lv):
        need |= {ord(c) for c in C.scan_asset_strings(p)}
    # Assembly-CSharp.dll 的 #US 字符串（代码里写死的 UI 文本，例如「大佬」的「佬」）
    from netmeta import PE, parse_us
    dllp = os.path.join(a.patch_dir, 'Managed', 'Assembly-CSharp.dll')
    if os.path.exists(dllp):
        dllchars = set()
        pe = PE(dllp)
        for s in parse_us(pe):
            dllchars |= {ord(c) for c in s}
        print(f'  DLL #US 字符串补充 {len(dllchars - need)} 个新码位')
        need |= dllchars
    need = {c for c in need if c >= 0x20 and not (0xD800 <= c <= 0xDFFF)}
    txt = ''.join(chr(c) for c in sorted(need))
    out = '_hanhua/out/bake_charset.txt'
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(txt)
    print(f'推荐重烤字符集: {len(need)} 个码位 -> {out}')
    print(f'  其中 汉字={sum(1 for c in need if 0x4E00<=c<=0x9FFF)} '
          f'假名={sum(1 for c in need if 0x3040<=c<=0x30FF)} '
          f'ASCII={sum(1 for c in need if 0x20<=c<=0x7E)} '
          f'全角={sum(1 for c in need if 0xFF01<=c<=0xFF5E)}')
    # 容量估算：8192^2 图集，字形按 96px 采样
    for px in (96, 80, 64):
        cap = (8192 // px) ** 2
        print(f'  单张 8192x8192 图集 @ {px}px 采样 ≈ 容纳 {cap} 字形 -> 需要 {-(-len(need)//cap)} 张')


if __name__ == '__main__':
    main()
