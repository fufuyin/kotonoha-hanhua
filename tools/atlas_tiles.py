#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把两份字体的图集各裁一块拼成对照 PNG（上半=补丁字体，下半=我们的字体），用于肉眼判断字体风格。

不做字形表反解，直接看图集像素（TMP 从左上角开始紧密排布字形）。

用法:
  python atlas_tiles.py --ref <patch.assets> --ref-atlas 0x53 \
      --our <our_raw.serialized> --out <png> [--w 2048] [--h 768] [--step 2]
"""
import os, struct, sys, argparse, zlib

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
from splice_fonts import find_pixels, obj_payload

PIX = 8192 * 8192


def write_png(path, w, h, gray):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += gray[y * w:(y + 1) * w]

    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 0, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(bytes(raw), 6))
    png += chunk(b'IEND', b'')
    open(path, 'wb').write(png)


def atlas_pixels(path, pid):
    f = UnityFile(path, verbose=False)
    o = [x for x in f.objects if (x['pathID'] & 0xFFFFFFFFFFFFFFFF) == pid][0]
    p = obj_payload(f, o)
    po, _ = find_pixels(p)
    return p[po:po + PIX]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ref', required=True)
    ap.add_argument('--ref-atlas', default='0x53')
    ap.add_argument('--our', required=True)
    ap.add_argument('--our-atlas', default=None)
    ap.add_argument('--out', required=True)
    ap.add_argument('--w', type=int, default=2048)
    ap.add_argument('--h', type=int, default=768)
    ap.add_argument('--step', type=int, default=2)
    ap.add_argument('--y0', type=int, default=0)
    a = ap.parse_args()

    pr = atlas_pixels(a.ref, int(a.ref_atlas, 16))
    if a.our_atlas:
        po = atlas_pixels(a.our, int(a.our_atlas, 16))
    else:
        f = UnityFile(a.our, verbose=False)
        o = [x for x in f.objects if x['classID'] == 28][0]
        p = obj_payload(f, o)
        off, _ = find_pixels(p)
        po = p[off:off + PIX]

    W, H = a.w // a.step, a.h // a.step
    gray = bytearray(W * H * 2)
    for part, px in ((0, pr), (1, po)):
        for j in range(H):
            src_y = a.y0 + j * a.step
            base = src_y * 8192
            for i in range(W):
                v = px[base + i * a.step]
                gray[(part * H + j) * W + i] = 255 - v   # 反相：白底黑字，便于观看
    write_png(a.out, W, H * 2, gray)
    print(f'[out] {a.out} {W}x{H*2}  (上半=补丁字体, 下半=我们的字体; 图集左上 {a.w}x{a.h} 区域)')


if __name__ == '__main__':
    main()
