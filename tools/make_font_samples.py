#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从两份字体资产里各取一组常用汉字，裁出图集字形拼成对照图（PNG），用于肉眼判断字体风格。

用法:
  python make_font_samples.py --ref <patch.assets> --ref-font 0xbe --ref-atlas 0x53 \
      --our <our_raw.serialized> --our-font <pathid> --our-atlas <pathid> --out <png>
"""
import os, struct, sys, argparse, zlib

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
from parse_tmp_font import detect_runs
from splice_fonts import find_pixels, obj_payload

PIX = 8192 * 8192
CHARS = '你好我是的了不在有人这中小上下来说话国日本汉字文字体测试员道具敌人保存设置标题退出金币'
GLYPH_SIZE = 68


def char_table(p):
    """返回 [(offset_of_record, unicode, glyphIndex)]（detect_runs 的表布局：+0 unicode, +4 glyphIndex）。"""
    runs = detect_runs(p, 64)
    if not runs:
        return []
    start, vals = max(runs, key=lambda r: len(r[1]))
    out = []
    n = len(vals)
    for k in range(n):
        off = start + k * 16
        if off + 16 > len(p):
            break
        u, gi = struct.unpack_from('<II', p, off)
        out.append((off, u, gi))
    return out


def find_glyph_rect(p, glyph_index):
    pat = struct.pack('<I', glyph_index)
    i = 0
    while True:
        i = p.find(pat, i)
        if i < 0:
            return None
        if i + GLYPH_SIZE <= len(p):
            x, y, w, h = struct.unpack_from('<iiii', p, i + 44)
            scale = struct.unpack_from('<f', p, i + 60)[0]
            ai = struct.unpack_from('<i', p, i + 64)[0]
            if 0 <= x < 8192 and 0 <= y < 8192 and 1 <= w <= 300 and 1 <= h <= 300 \
                    and abs(scale - 1.0) < 0.01 and ai == 0:
                return (x, y, w, h)
        i += 1


def load_ref(path, fpid, apid):
    f = UnityFile(path, verbose=False)
    fo = [o for o in f.objects if (o['pathID'] & 0xFFFFFFFFFFFFFFFF) == fpid][0]
    ao = [o for o in f.objects if (o['pathID'] & 0xFFFFFFFFFFFFFFFF) == apid][0]
    fp = obj_payload(f, fo)
    ap = obj_payload(f, ao)
    po, _ = find_pixels(ap)
    return fp, ap[po:po + PIX]


def write_png(path, w, h, gray):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += gray[y * w:(y + 1) * w]
    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 0, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(bytes(raw), 6))
    png += chunk(b'IEND', b'')
    open(path, 'wb').write(png)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ref', required=True)
    ap.add_argument('--ref-font', default='0xbe')
    ap.add_argument('--ref-atlas', default='0x53')
    ap.add_argument('--our', required=True)
    ap.add_argument('--our-font', default=None)
    ap.add_argument('--our-atlas', default=None)
    ap.add_argument('--out', required=True)
    ap.add_argument('--scale', type=int, default=3)
    a = ap.parse_args()

    fp_r, px_r = load_ref(a.ref, int(a.ref_font, 16), int(a.ref_atlas, 16))
    ct_r = {u: gi for _, u, gi in char_table(fp_r)}
    print(f'[ref] 字符表 {len(ct_r)} 个')

    O = UnityFile(a.our, verbose=False)
    fo = [o for o in O.objects if o['classID'] == 114][0]
    ao = [o for o in O.objects if o['classID'] == 28][0]
    fp_o = obj_payload(O, fo)
    px_o = obj_payload(O, ao)
    po, _ = find_pixels(px_o)
    px_o = px_o[po:po + PIX]
    ct_o = {u: gi for _, u, gi in char_table(fp_o)}
    print(f'[our] 字符表 {len(ct_o)} 个')

    S = a.scale
    CW, CH = 80, 80
    cols = 12
    rows_per = (len(CHARS) + cols - 1) // cols
    W = cols * CW
    H = rows_per * CH * 2 + 20
    gray = bytearray(W * H)   # 0 = 黑底

    def blit(px, rect, cx, cy, invert):
        x, y, w, h = rect
        for j in range(min(h, CH)):
            for i in range(min(w, CW)):
                v = px[(y + j) * 8192 + (x + i)]
                for sy in range(S):
                    for sx in range(S):
                        Y = cy + j * S + sy
                        X = cx + i * S + sx
                        if 0 <= Y < H and 0 <= X < W:
                            gray[Y * W + X] = 255 - v if invert else v

    miss = []
    for idx, ch in enumerate(CHARS):
        u = ord(ch)
        r = idx % cols
        c = idx // cols
        cx = r * CW + 8
        # 上半：补丁字体
        gi = ct_r.get(u)
        rect = find_glyph_rect(fp_r, gi) if gi is not None else None
        if rect:
            blit(px_r, rect, cx, c * CH * 2 + 8, True)
        else:
            miss.append((ch, 'ref'))
        # 下半：我们的字体
        gi2 = ct_o.get(u)
        rect2 = find_glyph_rect(fp_o, gi2) if gi2 is not None else None
        if rect2:
            blit(px_o, rect2, cx, c * CH * 2 + CH + 8, True)
        else:
            miss.append((ch, 'our'))
    print('缺失:', miss)
    write_png(a.out, W, H, gray)
    print(f'[out] {a.out} {W}x{H}  (上排=补丁字体, 下排=我们的字体)')


if __name__ == '__main__':
    main()
