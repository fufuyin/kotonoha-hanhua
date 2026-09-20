#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 raw bundle 里抽出 SerializedFile 存盘，并 dump 头部与元数据区字节，用于定位解析差异。
用法: python extract_serialized.py <bundle> <out.serialized>
"""
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bundle_extract import lz4_block


def main():
    src, dst = sys.argv[1], sys.argv[2]
    d = open(src, "rb").read()
    p = 8 + 4
    for _ in range(2):
        p = d.index(b"\x00", p) + 1
    size, cbis, ubis, flags = struct.unpack_from(">qIII", d, p); p += 20
    bi = lz4_block(d[p:p + cbis], ubis); p += cbis
    q = 16
    cnt = struct.unpack_from(">i", bi, q)[0]; q += 4
    blocks = []
    for _ in range(cnt):
        u, c, f = struct.unpack_from(">IIH", bi, q); q += 10
        blocks.append((u, c, f))
    data = bytearray()
    for (u, c, f) in blocks:
        assert (f & 0x3F) == 0, "block compressed"
        data += d[p:p + u]; p += u
    open(dst, "wb").write(bytes(data))
    print("wrote %s bytes=%d (blocks=%d)" % (dst, len(data), len(blocks)))

    ms, fs, ver, do = struct.unpack_from(">IIII", data, 0)
    print("header: metadataSize=%d fileSize=%d version=%d dataOffset=%d" % (ms, fs, ver, do))
    print("  dataOffset+?=%d  fileSize=%d  tailBytes=%d" % (do, fs, fs - do))
    for off in (16, 24, 32, 40, 48):
        u32 = struct.unpack_from(">I", data, off)[0]
        print("  off %2d: %s  u32=%d" % (off, data[off:off + 16].hex(), u32))
    print("  bytes[0:64] = " + data[:64].hex())
    print("  bytes[64:112]= " + data[64:112].hex())


if __name__ == "__main__":
    main()
