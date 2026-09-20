#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按 classID 切出对象 payload（可 hexdump），用于比对两边 TMP 字体资产的字段布局/版本串。

用法:
  python slice_objects.py <file> --class 114 [--class 28] [--out DIR] [--head 128]
"""
import os, struct, argparse, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile


def hexdump(buf, n, base_label='payload'):
    out = []
    for i in range(0, min(n, len(buf)), 16):
        chunk = buf[i:i + 16]
        hexs = ' '.join(f'{b:02x}' for b in chunk)
        asc = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        out.append(f'   {base_label}+{i:<5} {hexs:<47} |{asc}|')
    return '\n'.join(out)


def strings_in(buf, n, minlen=3):
    """在头部区域里找可打印串（含 Unity 字符串：i32 长度 + 字节）。"""
    out = []
    i = 0
    while i < n and i < len(buf) - 4:
        ln = struct.unpack_from('<i', buf, i)[0]
        if 1 <= ln <= 64 and i + 4 + ln <= len(buf):
            try:
                s = buf[i + 4:i + 4 + ln].decode('ascii')
                if s.isprintable():
                    out.append((i, s))
                    i += 4 + ln
                    continue
            except UnicodeDecodeError:
                pass
        i += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--class', dest='classes', type=int, action='append', default=[])
    ap.add_argument('--out', default=None)
    ap.add_argument('--head', type=int, default=0)
    a = ap.parse_args()
    if not a.classes:
        a.classes = [114]

    f = UnityFile(a.path, verbose=False)
    print(f'=== {os.path.basename(a.path)} objects={len(f.objects)} ===')
    if a.out:
        os.makedirs(a.out, exist_ok=True)
    idx = 0
    for o in f.objects:
        if o['classID'] not in a.classes:
            continue
        p = f.buf[o['abs']:o['abs'] + o['byteSize']]
        pid = o['pathID'] & 0xFFFFFFFFFFFFFFFF
        tag = f'c{o["classID"]}_{idx:02d}_{pid:016x}'
        print(f'--- {tag} size={o["byteSize"]} abs={o["abs"]} ---')
        if a.head:
            print(hexdump(p, a.head))
            ss = strings_in(p, max(a.head, 256))
            print('   头部内字符串(偏移,内容):', ss)
        if a.out:
            fn = os.path.join(a.out, tag + '.bin')
            open(fn, 'wb').write(p)
        idx += 1


if __name__ == '__main__':
    main()
