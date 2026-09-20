#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Unity .assets + .resS 导出 Texture2D 为 PNG（支持 DXT1/DXT5/RGBA32/RGB24/Alpha8）。
流式贴图的像素数据在 .resS 内，通过对象内的 m_StreamData(path, offset, size) 定位。

用法: python export_texture.py <file.assets> <name> <out.png> [--flip]
      python export_texture.py <file.assets> --list
"""
import sys, os, struct, zlib, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile, R


def d565(c):
    r = (c >> 11) & 0x1f
    g = (c >> 5) & 0x3f
    b = c & 0x1f
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))


def dxt_colors(c0, c1, dxt1):
    a0, b0, c0_ = d565(c0)
    a1, b1, c1_ = d565(c1)
    out = [(a0, b0, c0_, 255), (a1, b1, c1_, 255)]
    if not dxt1 or c0 > c1:
        out.append(((2*a0+a1)//3, (2*b0+b1)//3, (2*c0_+c1_)//3, 255))
        out.append(((a0+2*a1)//3, (b0+2*b1)//3, (c0_+2*c1_)//3, 255))
    else:
        out.append(((a0+a1)//2, (b0+b1)//2, (c0_+c1_)//2, 255))
        out.append((0, 0, 0, 0))
    return out


def decode(data, fmt, w, h, dxt1_if_bc1=True):
    """返回 RGBA bytes（top-down）"""
    out = bytearray(w*h*4)
    if fmt in (10, 12):   # DXT1 / DXT5
        bw, bh = max(1, (w+3)//4), max(1, (h+3)//4)
        bs = 8 if fmt == 10 else 16
        o = 0
        for by in range(bh):
            for bx in range(bw):
                blk = data[o:o+bs]; o += bs
                if len(blk) < bs:
                    break
                if fmt == 10:
                    c0, c1, bits = struct.unpack_from('<HHI', blk, 0)
                    cols = dxt_colors(c0, c1, True)
                else:
                    a0, a1 = blk[0], blk[1]
                    abits = struct.unpack_from('<Q', blk, 0)[0] >> 16
                    c0, c1, bits = struct.unpack_from('<HHI', blk, 8)
                    cols = dxt_colors(c0, c1, False)
                    for i in range(4):
                        pass
                for py in range(4):
                    for px in range(4):
                        x, y = bx*4+px, by*4+py
                        if x >= w or y >= h:
                            continue
                        idx = (bits >> (2*(4*py+px))) & 3
                        r, g, b, a = cols[idx]
                        if fmt == 12:
                            aidx = (abits >> (3*(4*py+px))) & 7
                            if a0 > a1:
                                a = a0 if aidx == 0 else (a1 if aidx == 1 else
                                    ((8-aidx)*a0 + (aidx-1)*a1)//7)
                            else:
                                a = a0 if aidx == 0 else (a1 if aidx == 1
                                    else (((6-aidx)*a0 + (aidx-1)*a1)//5 if aidx < 6 else (0 if aidx == 6 else 255)))
                        p = (y*w + x)*4
                        out[p:p+4] = bytes((r, g, b, a))
    elif fmt == 4:   # RGBA32
        out[:] = data[:w*h*4]
    elif fmt == 3:   # RGB24
        for i in range(w*h):
            out[i*4:i*4+3] = data[i*3:i*3+3]
            out[i*4+3] = 255
    elif fmt == 1:   # Alpha8
        for i in range(w*h):
            v = data[i] if i < len(data) else 0
            out[i*4:i*4+4] = bytes((v, v, v, 255))
    elif fmt == 14:  # BGRA32
        for i in range(w*h):
            b, g, r, a = data[i*4:i*4+4]
            out[i*4:i*4+4] = bytes((r, g, b, a))
    else:
        raise ValueError(f'unsupported format {fmt}')
    return bytes(out)


def write_png(path, w, h, rgba):
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    rows = b''.join(b'\x00' + rgba[y*w*4:(y+1)*w*4] for y in range(h))
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(rows, 6))
    png += chunk(b'IEND', b'')
    open(path, 'wb').write(png)


def parse_tex(f, o):
    r = R(f.buf, o['abs'])
    name = r.ustr().decode('utf-8', 'replace')
    forced = r.i32(); dfb = r.bool(); iap = r.bool(); r.align(4)
    w = r.i32(); h = r.i32(); cis = r.u32(); fmt = r.i32(); mips = r.i32()
    return dict(name=name, w=w, h=h, fmt=fmt, cis=cis, obj=o)


def get_stream(f, o):
    """定位 StreamingInfo：字段顺序为 offset(u32), size(u32), path(string)。"""
    raw = f.buf[o['abs']:o['abs']+o['byteSize']]
    i = raw.find(b'.resS\x00')
    if i < 0:
        return None
    path_end = i + 5                       # 含 '\0' 之后
    s = path_end
    while s > 0 and 0x20 <= raw[s-1] < 0x7f and path_end - s < 80:
        s -= 1
    ln = struct.unpack_from('<i', raw, s-4)[0] if s >= 4 else -1
    if ln != path_end - s:
        return None
    path = raw[s:path_end].rstrip(b'\0').decode('ascii', 'replace')
    off = struct.unpack_from('<I', raw, s-12)[0]
    size = struct.unpack_from('<I', raw, s-8)[0]
    return path, off, size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('name', nargs='?')
    ap.add_argument('out', nargs='?')
    ap.add_argument('--flip', action='store_true')
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args()
    f = UnityFile(a.path, verbose=False)
    texs = [parse_tex(f, o) for o in f.objects if o['classID'] == 28]
    if a.list:
        for t in texs[:50]:
            print(t['name'], t['w'], t['h'], t['fmt'])
        return
    cand = [t for t in texs if t['name'] == a.name]
    if not cand:
        cand = [t for t in texs if a.name.lower() in t['name'].lower()]
    if not cand:
        print('not found'); return
    t = cand[0]
    st = get_stream(f, t['obj'])
    if not st:
        print('no stream data (inline?) objSize=', t['obj']['byteSize']); return
    path, off, size = st
    res = os.path.join(os.path.dirname(a.path), os.path.basename(path))
    if not os.path.exists(res):
        res = os.path.join(os.path.dirname(a.path),
                           os.path.basename(a.path) + '.resS')
    data = open(res, 'rb').read()[off:off+size]
    print(f'tex {t["name"]} {t["w"]}x{t["h"]} fmt={t["fmt"]} stream={path} off={off} size={size} resS={os.path.basename(res)} got={len(data)}')
    rgba = decode(data, t['fmt'], t['w'], t['h'])
    w, h = t['w'], t['h']
    if a.flip:
        rows = [rgba[y*w*4:(y+1)*w*4] for y in range(h)][::-1]
        rgba = b''.join(rows)
    write_png(a.out, w, h, rgba)
    print('png ->', a.out)


if __name__ == '__main__':
    main()
