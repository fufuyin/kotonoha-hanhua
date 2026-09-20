#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在游戏文件中查找内嵌字体文件（sfnt/TrueType/OpenType），并解析其 name 表得到字体名。
判定方式：合法 sfnt 头 + 表目录（tag/checksum/offset/length）+ 纯表覆盖范围校验。

用法: python find_fonts.py <root> [--min-size 20000]
"""
import os, struct, argparse, sys

KNOWN_TAGS = {b'cmap', b'glyf', b'head', b'hhea', b'hmtx', b'loca', b'maxp', b'name',
              b'post', b'OS/2', b'CFF ', b'GPOS', b'GSUB', b'kern', b'DSIG', b'fpgm',
              b'prep', b'cvt ', b'VORG', b'EBDT', b'EBLC', b'GDEF', b'BASE', b'JSTF',
              b'MATH', b'gasp', b'hdmx', b'LTSH', b'VDMX', b'vhea', b'vmtx', b'PCLT',
              b'sbix', b'meta', b'STAT', b'HVAR', b'CFF2', b'avar', b'fvar', b'gvar'}


def parse_sfnt(buf, off):
    """返回 (numTables, [(tag, off, length)]) 或 None"""
    if off + 12 > len(buf):
        return None
    tag = buf[off:off+4]
    if tag not in (b'\x00\x01\x00\x00', b'OTTO', b'true', b'typ1'):
        return None
    num_tables = struct.unpack_from('>H', buf, off+4)[0]
    if not (4 <= num_tables <= 64):
        return None
    tables = []
    for i in range(num_tables):
        p = off + 12 + i*16
        if p + 16 > len(buf):
            return None
        t = buf[p:p+4]
        toff, tlen = struct.unpack_from('>II', buf, p+8)
        if t not in KNOWN_TAGS:
            return None
        if toff + tlen > len(buf) or tlen == 0 or tlen > 64*1024*1024:
            return None
        tables.append((t, toff, tlen))
    return num_tables, tables


def read_name_table(buf, base, tables):
    for tag, toff, tlen in tables:
        if tag != b'name':
            continue
        try:
            fmt, count, str_off = struct.unpack_from('>HHH', buf, base+toff)
        except Exception:
            return None
        names = {}
        for i in range(count):
            p = base + toff + 6 + i*12
            if p + 12 > len(buf):
                break
            pid, eid, lid, nid, ln, off = struct.unpack_from('>HHHHHH', buf, p)
            if nid not in (1, 2, 4, 6):
                continue
            s = base + toff + str_off + off
            raw = buf[s:s+ln]
            try:
                if pid == 3 and eid == 1:
                    txt = raw.decode('utf-16-be', 'replace')
                elif pid == 1 and eid == 0:
                    txt = raw.decode('latin1', 'replace')
                elif pid == 3 and eid == 10:
                    txt = raw.decode('utf-16-be', 'replace')
                else:
                    continue
            except Exception:
                continue
            if txt.strip():
                names.setdefault(nid, txt.strip())
        return names
    return None


def scan_file(path, min_size=20000):
    buf = open(path, 'rb').read()
    hits = []
    i = 0
    while True:
        # 候选起点：0x00010000 / OTTO / true
        idx = -1
        best = None
        for sig in (b'\x00\x01\x00\x00', b'OTTO', b'true'):
            j = buf.find(sig, i)
            if j >= 0 and (best is None or j < best):
                best = j
        if best is None:
            break
        i = best + 1
        r = parse_sfnt(buf, best)
        if not r:
            continue
        num_tables, tables = r
        total = max(t[1]+t[2] for t in tables) if tables else 0
        if total < min_size:
            continue
        nm = read_name_table(buf, best, tables)
        hits.append((best, total, num_tables, nm))
    return len(buf), hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root')
    ap.add_argument('--min-size', type=int, default=20000)
    a = ap.parse_args()
    exts = ('.assets', '.resS', '.resource', '.assets.resS')
    for dp, dn, fn in os.walk(a.root):
        for f in fn:
            p = os.path.join(dp, f)
            if not (f.endswith('.assets') or f.endswith('.resS') or f.endswith('.resource')
                    or f.startswith('level') or f == 'globalgamemanagers'):
                continue
            try:
                size, hits = scan_file(p, a.min_size)
            except Exception as e:
                print(f'ERR {p}: {e}', file=sys.stderr)
                continue
            if hits:
                print(f'--- {p} ({size} bytes)')
                for off, total, nt, nm in hits[:10]:
                    print(f'    offset={off} size≈{total} tables={nt} names={nm}')


if __name__ == '__main__':
    main()
