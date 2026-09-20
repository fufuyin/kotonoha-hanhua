#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提取补丁资源中「未翻译的日文串」及其精确位置。

方法：Unity 字符串序列化格式 = [i32 字节长度][UTF-8 字节][补齐到 4 字节]。
      只在对象数据内部按该格式逐条试探，命中即记录（偏移 = 内容起始，便于原地等长改写）。
过滤：含平假名/片假名（说明未翻译），长度 2..200，无 NUL。
排除：字体资产（>100KB 的 class 114）内的伪命中。

输出: _hanhua/out/untranslated.csv  (file, classID, pathID, objAbs, strOff, len, text)
用法: python extract_untranslated.py
"""
import os, sys, struct, csv, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile, CLASS_NAMES

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
OUT = os.path.join(ROOT, '_hanhua', 'out')
KANA = lambda s: any('\u3040' <= c <= '\u30ff' for c in s)


def unity_strings(raw, lo=2, hi=200):
    out = []
    i = 0
    n = len(raw)
    while i + 4 <= n:
        L = struct.unpack_from('<i', raw, i)[0]
        if lo <= L <= hi and i + 4 + L <= n:
            bs = raw[i + 4:i + 4 + L]
            if b'\x00' not in bs:
                try:
                    s = bs.decode('utf-8')
                except UnicodeDecodeError:
                    i += 1
                    continue
                if KANA(s):
                    out.append((i + 4, L, s))
                i += 4 + L
                i = (i + 3) & ~3
                continue
        i += 1
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    targets = [('resources.assets', os.path.join(ROOT, 'kotonoha_Data', 'resources.assets')),
               ('sharedassets0.assets', os.path.join(ROOT, 'kotonoha_Data', 'sharedassets0.assets'))]
    rows = []
    seen = set()
    for label, path in targets:
        if not os.path.exists(path):
            continue
        f = UnityFile(path, verbose=False)
        for o in f.objects:
            if o['classID'] == 114 and o['byteSize'] > 100000:
                continue          # 字体资产，跳过
            raw = f.buf[o['abs']:o['abs'] + o['byteSize']]
            if not raw:
                continue
            for off, ln, s in unity_strings(raw):
                key = (label, s)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(dict(file=label, cls=o['classID'],
                                 cname=CLASS_NAMES.get(o['classID'], '?'),
                                 pathID=hex(o['pathID']), objAbs=o['abs'],
                                 strOff=o['abs'] + off, length=ln, text=s))
    rows.sort(key=lambda r: (r['file'], r['objAbs'], r['strOff']))
    csv_path = os.path.join(OUT, 'untranslated.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f'未翻译日文串: {len(rows)} 条 -> {csv_path}')
    from collections import Counter
    c = Counter((r['file'], r['cname']) for r in rows)
    for k, v in c.most_common():
        print(f'   {k[0]:<22} {k[1]:<14} {v} 条')
    print('\n--- 前 80 条样例 ---')
    for r in rows[:80]:
        print(f"   [{r['file']} {r['cname']} @{r['strOff']}] {r['text']}")


if __name__ == '__main__':
    main()
