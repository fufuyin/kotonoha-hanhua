#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
汉化补丁缺字全量普查：
  A. 从补丁资源里提取所有 TMP 字体资产的已烘焙字符集（并集 + 逐字体）
  B. 从四个来源收集文本用到的字符：
     1) resources.assets 的 489 个 TextAsset（台词）
     2) resources.assets / sharedassets0.assets / level* 的 MonoBehaviour 字符串（UI/系统）
     3) Assembly-CSharp.dll 的 #US 字符串（程序内文本）
  C. 报告缺字（区分「排版符号类」与「真实汉字类」，便于决定修法）

用法: python check_coverage_all.py <patch_dir>
"""
import sys, os, re, glob, struct, argparse, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
import parse_tmp_font as PTF
from netmeta import PE, parse_us

CJK = re.compile(r'[\u3000-\u303F\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF00-\uFFEF\u2000-\u206F\u2190-\u21FF\u2460-\u24FF\u2500-\u257F]+')


def font_charsets_all(patch_dir):
    """返回 {文件: [(objSize, charset)]} 与并集"""
    per = {}
    union = set()
    for name in ('resources.assets', 'sharedassets0.assets'):
        p = os.path.join(patch_dir, name)
        if not os.path.exists(p):
            continue
        f = UnityFile(p, verbose=False)
        lst = []
        for o in f.objects:
            if o['classID'] != 114:
                continue
            raw = f.buf[o['abs']:o['abs'] + o['byteSize']]
            for start, vals in PTF.detect_runs(raw, 64):
                cs = set(vals)
                if len(cs) >= 500:
                    lst.append((o['byteSize'], o['abs'], cs))
                    union |= cs
        per[name] = lst
    return per, union


def scan_asset_strings(path, min_run=4):
    """从 .assets 原始字节里扫出 UTF-8 中文/日文串的字符集"""
    uf = UnityFile(path, verbose=False)
    chars = set()
    for o in uf.objects:
        raw = uf.buf[o['abs']:o['abs'] + o['byteSize']]
        if not raw:
            continue
        t = raw.decode('utf-8', 'ignore')
        for m in CJK.finditer(t):
            s = m.group(0)
            if len(s) >= min_run:
                chars |= set(s)
    return chars


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('patch_dir')
    ap.add_argument('--outdir', default='_hanhua/out')
    a = ap.parse_args()
    P = a.patch_dir

    print('=== A. 字体已烘焙字符集 ===')
    per, union = font_charsets_all(P)
    for name, lst in per.items():
        for sz, abs_, cs in lst:
            print(f'  {name} objSize={sz:>8} abs={abs_:>10} 字形表={len(cs)} 码位')
    print(f'  => 字体并集: {len(union)} 码位')

    print('\n=== B. 各来源文本字符集 ===')
    sources = collections.OrderedDict()
    # 1) 台词
    tp = os.path.join(a.outdir, 'patch_texts')
    cs = set()
    for p in glob.glob(os.path.join(tp, '*.txt')):
        cs |= set(open(p, encoding='utf-8', errors='ignore').read())
    sources['台词(489 TextAsset)'] = {c for c in cs if ord(c) > 0x7F}
    # 2) UI / 场景
    ui = set()
    for name in ('resources.assets', 'sharedassets0.assets'):
        p = os.path.join(P, name)
        if os.path.exists(p):
            ui |= scan_asset_strings(p)
    lv = set()
    lvfiles = [os.path.join(P, f) for f in os.listdir(P) if f.startswith('level') and '.' not in f]
    for p in sorted(lvfiles)[:130]:
        lv |= scan_asset_strings(p)
    sources['MonoBehaviour(UI/系统)'] = ui
    sources['level 场景'] = lv
    # 3) DLL
    dll = os.path.join(P, 'Managed', 'Assembly-CSharp.dll')
    dchars = set()
    if os.path.exists(dll):
        pe = PE(dll)
        for s in parse_us(pe):
            for ch in s:
                if ord(ch) > 0x7F:
                    dchars.add(ch)
    sources['Assembly-CSharp.dll'] = dchars

    allchars = set()
    for k, v in sources.items():
        print(f'  {k}: {len(v)} 个非 ASCII 字符')
        allchars |= v
    print(f'  => 全部来源合计: {len(allchars)} 个非 ASCII 字符')

    print('\n=== C. 缺字（按来源） ===')
    union_ord = set(union)          # 字体侧是码位整数
    seen = set()
    for k, v in sources.items():
        vi = {ord(c) for c in v}
        seen |= vi
        miss = sorted(vi - union_ord)
        print(f'  {k}: 用到 {len(vi)} 字符，缺 {len(miss)} 个')
        if miss:
            print('     ' + ''.join(chr(c) for c in miss[:80]))
    missing = sorted(seen - union_ord)
    print(f'\n  ===> 合计：用到 {len(seen)} 字符，字体覆盖 {len(seen & union_ord)}，缺 {len(missing)} 个')
    sym = [c for c in missing if not (0x4E00 <= ord(c) <= 0x9FFF)]
    han = [c for c in missing if 0x4E00 <= ord(c) <= 0x9FFF]
    print(f'  其中：真实汉字 {len(han)} 个，标点/符号/假名 {len(sym)} 个')
    if han:
        print('  缺的汉字:', ''.join(han))
    if sym:
        print('  缺的符号:', ''.join(sym))
    with open(os.path.join(a.outdir, 'missing_all.txt'), 'w', encoding='utf-8') as fh:
        fh.write(''.join(missing))
    print('  清单 ->', os.path.join(a.outdir, 'missing_all.txt'))


if __name__ == '__main__':
    main()
