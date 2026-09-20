#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探测 TMP 字体资产的 FaceInfo 与头部字符串（用于对比字号/行高/上下缘/源字体名）。

FaceInfo 签名：i32 pointSize(8..256) + f32 scale(0.5..2) + i32 unitsPerEM(256..4096)，
其后依次 lineHeight/ascentLine/descentLine/baseline/capLine/meanLine/...

用法: python probe_faceinfo.py <file> [--pathid 0xbe] [--all]
"""
import os, struct, sys, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
from probe_mat_props import read_ustr

FIELDS = ['pointSize', 'scale', 'lineHeight', 'ascentLine', 'descentLine', 'baseline',
          'capLine', 'meanLine', 'underlineOffset', 'underlineThickness', 'strikethroughOffset',
          'strikethroughThickness', 'superscriptOffset', 'superscriptSize', 'subscriptOffset',
          'subscriptSize', 'tabWidth']


def find_faceinfo(p):
    """签名: i32 pointSize(8..256) + f32 scale(0.5..2) + f32 lineHeight(0.5*ps..3*ps)。
    注意：TMP 2.0.1 的 FaceInfo **没有** unitsPerEM 字段（实测）。"""
    out = []
    for i in range(60, min(len(p) - 64, 600)):
        ps = struct.unpack_from('<i', p, i)[0]
        if not (8 <= ps <= 256):
            continue
        sc = struct.unpack_from('<f', p, i + 4)[0]
        if not (0.5 <= sc <= 2.0):
            continue
        lh = struct.unpack_from('<f', p, i + 8)[0]
        if not (0.5 * ps <= lh <= 3.0 * ps):
            continue
        out.append(i)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--pathid', default=None)
    ap.add_argument('--all', action='store_true')
    a = ap.parse_args()
    f = UnityFile(a.path, verbose=False)
    want = int(a.pathid, 16) if a.pathid else None
    print(f'=== {os.path.basename(a.path)} objects={len(f.objects)} ===')
    for o in f.objects:
        if o['classID'] != 114:
            continue
        pid = o['pathID'] & 0xFFFFFFFFFFFFFFFF
        if want is not None and pid != want:
            continue
        p = f.buf[o['abs']:o['abs'] + o['byteSize']]
        if want is None and not a.all and o['byteSize'] < 100000:
            continue
        nm_len = struct.unpack_from('<i', p, 28)[0]
        name = p[32:32 + nm_len].decode('utf-8', 'replace') if 1 <= nm_len <= 120 else '?'
        print(f'--- {name!r} 0x{pid:x} size={o["byteSize"]}')
        ss = []
        for off in range(0, min(len(p) - 8, 400)):
            r = read_ustr(p, off, lo=3, hi=64)
            if r:
                ss.append((off, r[0]))
        print('    头部字符串:', ss[:10])
        for fi in find_faceinfo(p):
            vals = [struct.unpack_from('<i', p, fi)[0], struct.unpack_from('<f', p, fi + 4)[0]]
            fl = [struct.unpack_from('<f', p, fi + 8 + 4 * k)[0] for k in range(15)]
            print(f'    FaceInfo@{fi}: ' + ' '.join(
                f'{k}={v:g}' for k, v in zip(FIELDS, vals + [round(x, 4) for x in fl])))
            ratio = fl[0] / vals[0] if vals[0] else 0
            print(f'      => lineHeight/pointSize = {ratio:.4f}; '
                  f'ascent={fl[1]:g}; descent={fl[2]:g}; capLine={fl[4]:g}; tabWidth={fl[14]:g}')


if __name__ == '__main__':
    main()
