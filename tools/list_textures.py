#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
列出 Texture2D 资产（名称/尺寸），用于判断 TMP 字体图集模式与图片内嵌文字风险。

Texture2D 序列化前导字段（Unity 2019.1, version 19）:
  m_Name(string), m_ForcedFallbackFormat(i32), m_DownscaleFallback(bool),
  m_IsAlphaChannelOptional(bool), m_Width(i32), m_Height(i32), m_CompleteImageSize(u32),
  m_TextureFormat(i32), ...

用法: python list_textures.py <file> [--filter SDF] [--csv out.csv]
"""
import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile, R

FORMATS = {1: 'Alpha8', 2: 'ARGB4444', 3: 'RGB24', 4: 'RGBA32', 5: 'ARGB32',
           7: 'RGB565', 10: 'DXT1', 12: 'DXT5', 13: 'RGBA4444', 14: 'BGRA32',
           30: 'BC4', 31: 'BC5', 34: 'ASTC_RGB', 47: 'ASTC_RGBA', 48: 'ASTC_RGBA_HDR',
           63: 'ETC2_RGBA8', 69: 'ETC2_RGBA8Crunched'}


def parse_tex(f, o):
    r = R(f.buf, o['abs'])
    name = r.ustr().decode('utf-8', 'replace')
    forced = r.i32()
    dfb = r.bool()
    iap = r.bool()
    r.align(4)
    w = r.i32(); h = r.i32()
    cis = r.u32()
    fmt = r.i32()
    mips = r.i32()
    return dict(name=name, w=w, h=h, completeImageSize=cis, fmt=FORMATS.get(fmt, fmt),
                mip=mips, size=o['byteSize'], abs=o['abs'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--filter', default=None)
    ap.add_argument('--csv', default=None)
    a = ap.parse_args()
    f = UnityFile(a.path, verbose=False)
    rows = []
    for o in f.objects:
        if o['classID'] != 28:
            continue
        try:
            t = parse_tex(f, o)
        except Exception as e:
            continue
        if a.filter and a.filter.lower() not in t['name'].lower():
            continue
        rows.append(t)
    print(f'== {a.path}: Texture2D matched={len(rows)} ==')
    for t in sorted(rows, key=lambda x: -(x['w']*x['h']))[:60]:
        print(f"  {t['w']:>5}x{t['h']:<5} {str(t['fmt']):<18} objSize={t['size']:>9} {t['name']!r}")
    if a.csv:
        import csv
        with open(a.csv, 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print('csv ->', a.csv)


if __name__ == '__main__':
    main()
