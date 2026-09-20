#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从任意 UnityFS bundle（数据块压缩或不压缩）取出 SerializedFile。

bundle_extract.py 只会处理未压缩数据块；本工具补上「数据块也压缩」的情况（LZ4 块级）。
用法: python bundle_serialized.py <bundle> <out.serialized>
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bundle_extract import lz4_block


def extract(path, out):
    d = open(path, 'rb').read()
    assert d[:8] == b'UnityFS\x00', 'not a UnityFS bundle'
    p = 8
    ver = struct.unpack_from('>i', d, p)[0]; p += 4
    strs = []
    for _ in range(2):
        e = d.index(b'\x00', p)
        strs.append(d[p:e].decode('latin-1'))
        p = e + 1
    size, cbis, ubis, flags = struct.unpack_from('>qIII', d, p); p += 20
    print(f'bundle={os.path.basename(path)} bytes={len(d)} version={ver} unity={strs[0]} rev={strs[1]}')
    print(f'  blocksInfo c={cbis} u={ubis} flags=0x{flags:x} dirComp={flags & 0x3F}')

    bi = d[p:p + cbis]; p += cbis
    if flags & 0x3F:
        bi = lz4_block(bi, ubis)
    q = 16
    if flags & 0x80:
        q += 4
    count = struct.unpack_from('>i', bi, q)[0]; q += 4
    blocks = []
    for _ in range(count):
        u, c, f = struct.unpack_from('>IIH', bi, q); q += 10
        blocks.append((u, c, f))
        print(f'  block u={u} c={c} comp={f & 0x3F}')

    data = bytearray()
    for (u, c, f) in blocks:
        chunk = d[p:p + c]
        if f & 0x3F:
            chunk = lz4_block(chunk, u)
        else:
            chunk = chunk[:u]
        data += chunk
        p += c
    open(out, 'wb').write(bytes(data))
    print(f'  serialized -> {out} ({len(data)} bytes)')
    return len(data)


if __name__ == '__main__':
    sys.exit(0 if extract(sys.argv[1], sys.argv[2]) else 1)
