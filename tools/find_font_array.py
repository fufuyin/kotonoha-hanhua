#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
定位场景里的「4 元素字体数组」（NobelUIScript.fontAsset：japan/raysant/spirit/other 各一支字体）。

思路：该数组是连续的 4 个 PPtr（各 12 字节：fileID i32 + pathID i64），其 pathID 正好是
      sharedassets0 里那 4 支字体资产的 pathID（0xbe/0xbf/0xc0/0xc1），且四者互不相同。
用法: python find_font_array.py [--rewrite-to-gyate]
"""
import os, sys, glob, struct, argparse, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
DATA = os.path.join(ROOT, 'kotonoha_Data')
GYATE = 0xbe                      # 212484 那支（前作者的中文字体）
OTHERS = (0xbf, 0xc0, 0xc1)       # Makinas / RiiPopkkR / Stick_Regular（日文字形表）


def level_files():
    fs = [p for p in glob.glob(os.path.join(DATA, 'level*')) if '.' not in os.path.basename(p)]
    return sorted(fs, key=lambda p: int(''.join(c for c in os.path.basename(p) if c.isdigit()) or 0))


def scan(path):
    b = open(path, 'rb').read()
    pat = struct.pack('<q', GYATE)
    out = []
    pos = 0
    while True:
        i = b.find(pat, pos)
        if i < 0:
            break
        pos = i + 1
        seq, ok = [], True
        for k in range(4):
            o = i + k * 12
            if o + 8 > len(b):
                ok = False
                break
            seq.append(struct.unpack_from('<q', b, o)[0])
        if ok and all(s in (GYATE,) + OTHERS for s in seq) and len(set(seq)) == 4:
            fid = struct.unpack_from('<i', b, i - 4)[0] if i >= 4 else None
            out.append((i, fid, seq))
    return b, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rewrite-to-gyate', action='store_true',
                    help='把数组里后 3 项（非 Gyate）改写成 Gyate 的 pathID')
    a = ap.parse_args()
    total = 0
    for p in level_files():
        b, hits = scan(p)
        if not hits:
            continue
        total += len(hits)
        print(f'--- {os.path.basename(p)}: {len(hits)} 处')
        for i, fid, seq in hits:
            print(f'     @{i} fileID={fid} pathIDs={[hex(s) for s in seq]}')
        if a.rewrite_to_gyate:
            buf = bytearray(b)
            for i, fid, seq in hits:
                for k in range(4):
                    o = i + k * 12
                    if struct.unpack_from('<q', buf, o)[0] != GYATE:
                        struct.pack_into('<q', buf, o, GYATE)
            bk = os.path.join(ROOT, '_hanhua', 'backup', os.path.basename(p) + '.before_fontarr')
            if not os.path.exists(bk):
                shutil.copyfile(p, bk)
            open(p, 'wb').write(bytes(buf))
            b2, hits2 = scan(p)
            print(f'     [write] 已改写，复查剩余数组数={len(hits2)} 大小={os.path.getsize(p)}')
    print(f'\n合计数组: {total}')


if __name__ == '__main__':
    main()
