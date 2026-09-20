#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
把 resources.assets 里的 GDhwGoJA 图集对象（0x1ff3）从"流式(.resS)"改成"内联像素"，
这样交付包不再需要带 919MB 的 resources.assets.resS。

实测布局（名字 27 字符 -> 名前缀 32 字节，与 Gyate 图集偏移一致）：
  +0..107  头部（name/4/0/width/height/completeSize/format/mip/.../platformBlob count）
  +108     m_ImageData 的 count（流式时 = 0；内联时 = 67108864）→ 紧接着是像素
  像素之后  m_StreamData = [u32 offset][u32 size][i32 pathLen][path]
目标 payload 长度 = 112 + 67108864 + 12 = 67108988（与 sharedassets0 里两张内联图集完全相同 ✓）

用法: python inline_gd_atlas.py --res <resources.assets> --out <out.assets> --golden <bin>
"""
import os, sys, struct, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from unityfile import UnityFile
from splice_fonts import obj_payload, find_pixels
from splice_more import Editor

PID = 0x1FF3
PIX = 8192 * 8192
GD_RES_OFFSET = 852033564      # 实测：1c 00 c9 32 (LE) = 0x32C9001C；+PIX 正好等于 .resS 文件长度
GD_RES_OFFSET_WRONG = 851443740  # 曾误算的偏移（写它会污染别的贴图，见文档 §10.7）


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--res', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--golden', default=r'F:\Application\Unity\twobake_atlas.bin')
    ap.add_argument('--probe', action='store_true', help='只打印计划，不写文件')
    a = ap.parse_args()

    E = Editor(a.res)
    o = E.obj(PID)
    p = E.payload(o)
    name_len = struct.unpack_from('<i', p, 0)[0]
    name = p[4:4 + name_len].decode('utf-8')
    off, size, plen = struct.unpack_from('<IIi', p, 112)
    cnt = struct.unpack_from('<i', p, 108)[0]
    print(f'[atlas] {name!r} payload={len(p)} name_len={name_len}')
    print(f'[atlas] m_ImageData count={cnt}  m_StreamData: offset={off} size={size} pathLen={plen}')
    assert name == 'GDhwGoJA-OTF112b2 SDF Atlas', name
    assert len(p) == 148 and cnt == 0, '该对象已经内联过，无需再改'
    assert off == GD_RES_OFFSET and size == PIX and plen == len('resources.assets.resS')

    golden = open(a.golden, 'rb').read()
    assert len(golden) == PIX
    # 注意：这里**不做** ".resS 里那份像素 == 黄金像素" 的比对——.resS 里那份是补丁作者的旧图集；
    # 内联的意义正是"用我们自己的像素取代它"，所以只需确认 .resS 至少有那一整块空间。
    print('[atlas] 将把黄金像素内联进 assets（.resS 里那份旧图集不再被引用）')

    new = bytearray(p[:108])
    new += struct.pack('<i', PIX)               # m_ImageData count
    new += golden                               # 像素
    new += struct.pack('<I', 0)                 # m_StreamData.offset
    new += struct.pack('<I', 0)                 # m_StreamData.size
    new += struct.pack('<i', 0)                 # m_StreamData.pathLen (空路径)
    print(f'[atlas] 内联后 payload = {len(new)} B (期望 {112 + PIX + 12})')
    assert len(new) == 112 + PIX + 12

    if not a.probe:
        E.add_font(o, bytes(new))
        open(a.out, 'wb').write(E.finish())
        print(f'[out] {a.out} ({os.path.getsize(a.out)} bytes)')

    # ---------------- 独立校验 ----------------
    A = UnityFile(a.res, verbose=False)
    B = UnityFile(a.out, verbose=False)
    assert len(A.objects) == len(B.objects) == 35760
    changed = []
    for oa, ob in zip(A.objects, B.objects):
        pid = oa['pathID'] & 0xFFFFFFFFFFFFFFFF
        if (oa['byteStart'], oa['byteSize']) != (ob['byteStart'], ob['byteSize']) \
                or obj_payload(A, oa) != obj_payload(B, ob):
            changed.append(hex(pid))
    print('[verify] 变化对象:', changed)
    assert changed == ['0x1ff3'], changed
    ob = [x for x in B.objects if (x['pathID'] & 0xFFFFFFFFFFFFFFFF) == PID][0]
    pb = obj_payload(B, ob)
    nl2 = struct.unpack_from('<i', pb, 0)[0]
    nm2 = pb[4:4 + nl2].decode('utf-8')
    w, h = struct.unpack_from('<ii', pb, 40)
    fmt = struct.unpack_from('<i', pb, 52)[0]
    cnt2 = struct.unpack_from('<i', pb, 108)[0]
    px = pb[112:112 + PIX]
    off2, size2, plen2 = struct.unpack_from('<IIi', pb, 112 + PIX)
    print(f'[verify] {nm2!r} {w}x{h} format={fmt} count={cnt2} 尾部 stream=({off2},{size2},{plen2})')
    ok = (nm2 == name and w == 8192 and h == 8192 and fmt == 1 and cnt2 == PIX
          and px == golden and off2 == 0 and size2 == 0 and plen2 == 0
          and B.file_size == len(B.buf))
    print('[verify] fileSize头:', B.file_size, '实际:', len(B.buf))
    print('RESULT:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
