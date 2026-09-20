#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
正确读取 TMP_FontAsset 的字符表（不依赖码位排序）。

背景：TMP 的 m_CharacterTable 不保证按 unicode 升序存储，因此用"码位递增游程"来探测
      会漏掉乱序条目（即把实际存在的字误判成缺字）。正确的判据是 **字形索引递增**：
      记录布局 = [unicode u32][glyphIndex u32][scale f32][u32]，glyphIndex 按插入顺序单调递增。

做法：
  1. 先用码位游程找到一个种子条目
  2. 以种子为起点，按 glyphIndex 单调性向前/向后走，找出整张表
  3. 读取表头 count 并校验 (end-start)/16 == count
用法: python read_tmp_charset.py
"""
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
import parse_tmp_font as PTF

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
OUT = os.path.join(ROOT, '_hanhua', 'out')
REC = 16


def u32(raw, off):
    return struct.unpack_from('<I', raw, off)[0]


def read_table(raw, seed_off):
    """从种子条目出发，按 glyphIndex 单调性还原整张表；返回 (start, count, [code points])"""
    n = len(raw)
    seed_gi = u32(raw, seed_off + 4)

    # 向前走（glyphIndex 递减）
    start = seed_off
    while start - REC >= 0:
        gi = u32(raw, start - REC + 4)
        u = u32(raw, start - REC)
        if gi + 1 == u32(raw, start + 4) and 0x20 <= u <= 0x10FFFF:
            start -= REC
        else:
            break
    # 向后走（glyphIndex 递增）
    end = seed_off + REC
    while end + REC <= n:
        gi = u32(raw, end + 4)
        u = u32(raw, end)
        if gi == u32(raw, end - REC + 4) + 1 and 0x20 <= u <= 0x10FFFF:
            end += REC
        else:
            break

    count = (end - start) // REC
    hdr = struct.unpack_from('<i', raw, start - 4)[0] if start >= 4 else -1
    cps = [u32(raw, start + i * REC) for i in range(count)]
    return start, count, cps, hdr


def main():
    os.makedirs(OUT, exist_ok=True)
    report = []
    for path, label in ((os.path.join(ROOT, 'kotonoha_Data', 'sharedassets0.assets'), 'sharedassets0'),
                        (os.path.join(ROOT, 'kotonoha_Data', 'resources.assets'), 'resources')):
        f = UnityFile(path, verbose=False)
        for o in f.objects:
            if o['classID'] != 114 or o['byteSize'] < 100000:
                continue
            raw = f.buf[o['abs']:o['abs'] + o['byteSize']]
            # 用码位游程找种子（取最长游程的第一条）
            runs = PTF.detect_runs(raw, 64)
            if not runs:
                continue
            seed = max(runs, key=lambda r: len(r[1]))[0]
            start, count, cps, hdr = read_table(raw, seed)
            cs = set(cps)
            line = (f'{label}:{o["byteSize"]}  表起点={start} 条目={count} 表头count={hdr} '
                    f'码位范围=U+{min(cps):04X}..U+{max(cps):04X} '
                    f'含ASCII={0x41 in cs} 含数字={0x30 in cs} 含全角括号={0xFF08 in cs} '
                    f'含汉字={0x4E00 in cs}')
            print(line)
            report.append(line)
            with open(os.path.join(OUT, f'charset_{label}_{o["byteSize"]}.txt'), 'w', encoding='utf-8') as fh:
                fh.write(''.join(chr(c) for c in sorted(cs)))
    with open(os.path.join(OUT, 'charset_report.txt'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(report))
    print('\n字符集已导出到 _hanhua/out/charset_*.txt')


if __name__ == '__main__':
    main()
