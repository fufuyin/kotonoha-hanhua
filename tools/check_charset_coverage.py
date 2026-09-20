#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
核对某字体资产是否覆盖指定字符集文件（如 F:\Application\Unity\charset.txt）。

用法: python check_charset_coverage.py <serialized|assets> <charset.txt>
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from unityfile import UnityFile
from parse_tmp_font import detect_runs
from splice_fonts import obj_payload


def baked_chars(path):
    f = UnityFile(path, verbose=False)
    total, per = set(), []
    for o in f.objects:
        if o['classID'] != 114:
            continue
        p = obj_payload(f, o)
        runs = detect_runs(p, 64)
        s = set()
        for _, vals in runs:
            s |= set(vals)
        if s:
            per.append((o['byteSize'], len(s)))
        total |= s
    return total, per


def main():
    font_file, charset_file = sys.argv[1], sys.argv[2]
    want = set()
    with open(charset_file, encoding='utf-8') as fh:
        for ch in fh.read():
            o = ord(ch)
            if o > 0x20:
                want.add(o)
    got, per = baked_chars(font_file)
    print(f'charset.txt 需要的码位: {len(want)}')
    print(f'{os.path.basename(font_file)} 已烘焙码位: {len(got)}')
    missing = sorted(want - got)
    extra = sorted(got - want)
    print(f'缺字 {len(missing)}；多出 {len(extra)}')
    if missing:
        print('缺字示例:', ''.join(chr(c) for c in missing[:120]))
        print('（注意：charset.txt 里本身有约 850 个码位在两份源字体里都不存在，属于已知不可烤项）')
    for size, n in sorted(per, reverse=True)[:4]:
        print(f'  字体对象 size={size} 码位={n}')


if __name__ == '__main__':
    main()
