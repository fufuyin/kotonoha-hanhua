#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读 TTF/OTF 的 head/hhea/OS-2 表，输出纵向度量比值（用于与 TMP FaceInfo 剖面匹配字体）。

用法: python font_metrics.py <font_or_dir> [...]
"""
import os, struct, sys, glob

KNOWN = {b'head', b'hhea', b'OS/2', b'cmap', b'name', b'CFF ', b'glyf', b'loca', b'maxp',
         b'post', b'hmtx', b'GSUB', b'GPOS', b'vhea', b'vmtx', b'VORG', b'kern', b'BASE'}


def read_tables(buf, off):
    if buf[off:off + 4] not in (b'\x00\x01\x00\x00', b'OTTO', b'true'):
        return None
    n = struct.unpack_from('>H', buf, off + 4)[0]
    tabs = {}
    for i in range(n):
        p = off + 12 + i * 16
        if p + 16 > len(buf):
            return None
        tag = buf[p:p + 4]
        toff, tlen = struct.unpack_from('>II', buf, p + 8)
        if tag in KNOWN and toff + tlen <= len(buf):
            tabs[tag] = (toff, tlen)
    return tabs


def name_of(buf, tabs):
    if b'name' not in tabs:
        return '?'
    off, _ = tabs[b'name']
    try:
        fmt, count, so = struct.unpack_from('>HHH', buf, off)
    except Exception:
        return '?'
    best = '?'
    for i in range(count):
        p = off + 6 + i * 12
        if p + 12 > len(buf):
            break
        pid, eid, lid, nid, ln, o = struct.unpack_from('>HHHHHH', buf, p)
        if nid in (1, 4) and pid == 3 and eid in (1, 10):
            raw = buf[off + so + o:off + so + o + ln]
            try:
                s = raw.decode('utf-16-be', 'replace')
            except Exception:
                continue
            if nid == 1 or (nid == 4 and len(s) > len(best)):
                if nid == 1:
                    best = s
    return best.strip()


def metrics(path):
    buf = open(path, 'rb').read()
    idx = [i for i in (buf.find(b'\x00\x01\x00\x00'), buf.find(b'OTTO'), buf.find(b'true')) if i >= 0]
    if not idx:
        return None
    tabs = read_tables(buf, min(i for i in idx if read_tables(buf, i) is not None)) if idx else None
    if not tabs:
        return None
    upem = struct.unpack_from('>H', buf, tabs[b'head'][0] + 18)[0] if b'head' in tabs else None
    asc = dsc = gap = cap = xh = None
    if b'hhea' in tabs:
        off, _ = tabs[b'hhea']
        asc, dsc, gap = struct.unpack_from('>hhh', buf, off + 4)
    if b'OS/2' in tabs:
        off, _ = tabs[b'OS/2']
        ver = struct.unpack_from('>H', buf, off)[0]
        if ver >= 2 and off + 90 <= len(buf):
            xh = struct.unpack_from('>h', buf, off + 86)[0]
            cap = struct.unpack_from('>h', buf, off + 88)[0]
    return dict(name=name_of(buf, tabs), upem=upem, asc=asc, dsc=dsc, gap=gap, cap=cap, xh=xh)


PATCH = (0.85938, 0.14063, 0.66471, 0.51765)   # 补丁字体的 FaceInfo 比值


def main():
    paths = []
    for a in sys.argv[1:]:
        if os.path.isdir(a):
            for ext in ('*.ttf', '*.otf', '*.ttc', '*.TTF', '*.OTF'):
                paths += glob.glob(os.path.join(a, '**', ext), recursive=True)
        else:
            paths.append(a)
    print(f'目标剖面（补丁字体）= ascent {PATCH[0]:.5f} / descent {PATCH[1]:.5f} / '
          f'capHeight {PATCH[2]:.5f} / xHeight {PATCH[3]:.5f}')
    for p in paths:
        try:
            m = metrics(p)
        except Exception as e:
            print(f'ERR {os.path.basename(p)}: {e}')
            continue
        if not m or not m['upem'] or m['asc'] is None:
            print(f'  {os.path.basename(p)}: 读不到度量')
            continue
        u = float(m['upem'])
        a, d = m['asc'] / u, -m['dsc'] / u
        c = (m['cap'] / u) if m['cap'] else None
        x = (m['xh'] / u) if m['xh'] else None
        dist = abs(a - PATCH[0]) + abs(d - PATCH[1]) + (abs(c - PATCH[2]) if c else 0)
        print(f'  {os.path.basename(p)}: name={m["name"]!r} upem={m["upem"]} '
              f'ascent={a:.5f} descent={d:.5f} lineGap={m["gap"]} '
              f'cap={c if c is None else round(c,5)} x={x if x is None else round(x,5)} 距离={dist:.4f}')


if __name__ == '__main__':
    main()
