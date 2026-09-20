#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探测 Material 的 TMP SDF 属性（_GradientScale / _TextureWidth / _OutlineWidth / _OutlineColor ...）。

不需要类型树：Material 的 m_SavedProperties 里每个属性都是「Unity 字符串(名字) + 值」，
名字是唯一锚点，所以扫字符串、再解析紧随其后的 float / Color 即可。

用法: python probe_mat_props.py <file> [--filter 关键词] [--pathid 0x..]
"""
import os, struct, sys, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile

KEY_FLOATS = ['_GradientScale', '_TextureWidth', '_TextureHeight', '_ScaleRatioA', '_ScaleRatioB',
              '_ScaleRatioC', '_ScaleX', '_ScaleY', '_FaceDilate', '_OutlineWidth', '_OutlineSoftness',
              '_UnderlayOffsetX', '_UnderlayOffsetY', '_UnderlayDilate', '_UnderlaySoftness',
              '_PerspectiveFilter', '_Sharpness', '_WeightNormal', '_WeightBold',
              '_VertexOffsetX', '_VertexOffsetY', '_GlowPower', '_GlowOffset', '_GlowDilate']
KEY_COLORS = ['_FaceColor', '_OutlineColor', '_UnderlayColor', '_GlowColor', '_Color']


def u32(b, o):
    return struct.unpack_from('<i', b, o)[0]


def f32(b, o):
    return struct.unpack_from('<f', b, o)[0]


def read_ustr(b, o, lo=3, hi=40):
    """尝试把 o 处当成 Unity 字符串读，成功返回 (name, next_off)。"""
    if o + 4 > len(b):
        return None
    n = u32(b, o)
    if not (lo <= n <= hi) or o + 4 + n > len(b):
        return None
    raw = b[o + 4:o + 4 + n]
    try:
        s = raw.decode('ascii')
    except UnicodeDecodeError:
        return None
    if not (s[0] == '_' or s[0].isalnum()):
        return None
    if not all(32 <= c < 127 for c in raw):
        return None
    nxt = (o + 4 + n + 3) & ~3
    return s, nxt


def scan_props(p):
    floats, colors = {}, {}
    i = 0
    while i < len(p) - 8:
        r = read_ustr(p, i)
        if r:
            name, nxt = r
            if name in KEY_FLOATS and nxt + 4 <= len(p):
                v = f32(p, nxt)
                if -1e6 < v < 1e6:
                    floats[name] = v
            elif name in KEY_COLORS and nxt + 16 <= len(p):
                c = [f32(p, nxt + 4 * k) for k in range(4)]
                if all(-0.01 <= x <= 4.0 for x in c):
                    colors[name] = tuple(round(x, 4) for x in c)
            i = nxt
        else:
            i += 1
    return floats, colors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--filter', default=None)
    ap.add_argument('--pathid', default=None)
    ap.add_argument('--only-key', action='store_true', help='只打印关键属性（默认全部属性）')
    a = ap.parse_args()

    f = UnityFile(a.path, verbose=False)
    print(f'=== {os.path.basename(a.path)} objects={len(f.objects)} ===')
    want = int(a.pathid, 16) if a.pathid else None
    for o in f.objects:
        if o['classID'] != 21:
            continue
        if want is not None and (o['pathID'] & 0xFFFFFFFFFFFFFFFF) != want:
            continue
        p = f.buf[o['abs']:o['abs'] + o['byteSize']]
        pid = o['pathID'] & 0xFFFFFFFFFFFFFFFF
        name = '?'
        for off in (0, 4):
            r = read_ustr(p, off, lo=1, hi=80)
            if r:
                name = r[0]
                break
        if a.filter and a.filter.lower() not in name.lower():
            continue
        fl, co = scan_props(p)
        print(f'--- {name} (0x{pid:x}, {o["byteSize"]}B)')
        if fl:
            print('    floats:', ' '.join(f'{k}={v:g}' for k, v in fl.items()))
        if co:
            print('    colors:', ' '.join(f'{k}={v}' for k, v in co.items()))


if __name__ == '__main__':
    main()
