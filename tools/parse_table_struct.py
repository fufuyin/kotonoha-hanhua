#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结构化定位 TMP_FontAsset 的 m_CharacterTable（第三种方法：结构打分，不依赖排序）。

记录布局（实测）: [unicode u32][glyphIndex u32][scale f32][u32]，逐条 16 字节；
表头为 [count i32]。扫描所有偏移，以「count 合理 + count 条记录结构合法」打分取最优。

用法: python parse_table_struct.py
"""
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
OUT = os.path.join(ROOT, '_hanhua', 'out')


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def score(raw, s, c, probe=120):
    """返回 (命中率, 实际条目数)"""
    n = len(raw)
    if s < 4 or s + c * 16 > n:
        return 0.0, c
    good = 0
    k = 0
    while k < c and k < probe:
        off = s + k * 16
        u = u32(raw, off)
        gi = u32(raw, off + 4)
        sc = struct.unpack_from('<f', raw, off + 8)[0]
        x = u32(raw, off + 12)
        if 0x20 <= u <= 0x10FFFF and gi <= 100000 and (sc == 1.0 or sc == 0.0) and x <= 0x100000:
            good += 1
        k += 1
    return good / float(min(c, probe)), c


def find_table(raw):
    n = len(raw)
    best = (0.0, -1, 0)
    for s in range(4, n - 16, 4):
        c = u32(raw, s - 4)
        if not (100 <= c <= 30000):
            continue
        if s + c * 16 > n:
            continue
        r, _ = score(raw, s, c)
        if r > best[0]:
            best = (r, s, c)
            if r >= 0.999:
                break
    return best


def main():
    for path, label in ((os.path.join(ROOT, 'kotonoha_Data', 'sharedassets0.assets'), 'sharedassets0'),
                        (os.path.join(ROOT, 'kotonoha_Data', 'resources.assets'), 'resources')):
        f = UnityFile(path, verbose=False)
        for o in f.objects:
            if o['classID'] != 114 or o['byteSize'] < 100000:
                continue
            raw = f.buf[o['abs']:o['abs'] + o['byteSize']]
            r, s, c = find_table(raw)
            if s < 0:
                print(f'{label}:{o["byteSize"]}  未找到字符表')
                continue
            cps = [u32(raw, s + i * 16) for i in range(c)]
            cs = set(cps)
            print(f'{label}:{o["byteSize"]}  命中率={r:.3f} 表起点={s} 条目={len(cps)} '
                  f'码位范围=U+{min(cps):04X}..U+{max(cps):04X}')
            checks = [('！', 0xFF01), ('？', 0xFF1F), ('，', 0xFF0C), ('（', 0xFF08), ('）', 0xFF09),
                      ('～', 0xFF5E), ('〜', 0x301C), ('…', 0x2026), ('・', 0x30FB), ('—', 0x2014),
                      ('·', 0x00B7), ('的', 0x7684), ('这', 0x8FD9), ('们', 0x4EEC), ('A', 0x41), ('0', 0x30)]
            print('     ' + '  '.join(f'{ch}{"✓" if cp in cs else "✗"}' for ch, cp in checks))
            with open(os.path.join(OUT, f'charset2_{label}_{o["byteSize"]}.txt'), 'w', encoding='utf-8') as fh:
                fh.write(''.join(chr(x) for x in sorted(cs)))


if __name__ == '__main__':
    main()
