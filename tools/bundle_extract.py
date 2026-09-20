#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从未压缩 AssetBundle(UnityFS) 里取出 SerializedFile，列出对象表 —— 用于定位我们烤出来的
TMP 字体资产(class 114)/图集(class 28)/材质(class 21) 的 pathID 与 payload 大小。

要点（两个坑都踩过）：
  * UnityFS 头里是**两个** null 结尾字符串：unityVersion 与 unityRevision
  * 头里 flags & 0x3F 是**目录信息(blocksInfo)**的压缩方式；数据块各带自己的 flags。
    即使 BuildAssetBundleOptions.UncompressedAssetBundle，目录信息仍可能被 LZ4HC 压缩
    （本工程实测 91 -> 65 字节），所以必须实现 LZ4 块解压才能拿到块表。

用法: python bundle_extract.py <bundle> [--dump <classID> <pathID> <out.bin>]
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile, CLASS_NAMES

NAMES = {21: "Material", 28: "Texture2D", 48: "Shader", 114: "MonoBehaviour", 115: "MonoScript", 142: "AssetBundle"}


def lz4_block(src, expected=None):
    """标准 LZ4 块解压（纯 Python，够用）。"""
    out = bytearray()
    i = 0
    n = len(src)
    while i < n:
        token = src[i]; i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = src[i]; i += 1; lit += b
                if b != 255:
                    break
        out += src[i:i + lit]; i += lit
        if i >= n:
            break
        off = src[i] | (src[i + 1] << 8); i += 2
        mlen = token & 0x0F
        if mlen == 15:
            while True:
                b = src[i]; i += 1; mlen += b
                if b != 255:
                    break
        mlen += 4
        start = len(out) - off
        if start < 0:
            raise ValueError("bad LZ4 offset")
        for k in range(mlen):
            out.append(out[start + k])
    if expected is not None and len(out) != expected:
        raise ValueError("LZ4 size mismatch: got %d want %d" % (len(out), expected))
    return bytes(out)


def extract(path):
    d = open(path, "rb").read()
    print("bundle=%s bytes=%d" % (os.path.basename(path), len(d)))
    assert d[:8] == b"UnityFS\x00", "not a UnityFS bundle"
    p = 8
    version = struct.unpack_from(">i", d, p)[0]; p += 4
    strings = []
    for _ in range(2):
        e = d.index(b"\x00", p)
        strings.append(d[p:e].decode("latin-1")); p = e + 1
    size, cbis, ubis, flags = struct.unpack_from(">qIII", d, p); p += 20
    print("  version=%d unity=%s rev=%s size=%d" % (version, strings[0], strings[1], size))
    print("  blocksInfo compressed=%d uncompressed=%d flags=0x%x (dirComp=%d)" % (cbis, ubis, flags, flags & 0x3F))

    bi = d[p:p + cbis]
    p += cbis
    if flags & 0x3F:
        bi = lz4_block(bi, ubis)
        print("  blocksInfo decompressed -> %d bytes" % len(bi))
    # 实测（Unity 2019.1 / UnityFS v6）目录信息布局（以 as u32 解析为准）：
    #   [16 字节保留/哈希] u32 block_count, 每块(u32 uSize,u32 cSize,u16 flags),
    #   然后 u32 node_count + 若干 node(i64 offset,i64 size,u32 flags,cstr path)
    q = 16
    if flags & 0x80:
        q += 4
    count = struct.unpack_from(">i", bi, q)[0]; q += 4
    print("  data blocks=%d" % count)
    blocks = []
    for _ in range(count):
        u, c, f = struct.unpack_from(">IIH", bi, q); q += 10
        blocks.append((u, c, f))
        print("     block u=%d c=%d comp=%d" % (u, c, f & 0x3F))

    data = bytearray()
    for (u, c, f) in blocks:
        if f & 0x3F:
            raise AssertionError("数据块也是压缩的（comp=%d）——需要先用 UncompressedAssetBundle 打包" % (f & 0x3F))
        data += d[p:p + u]
        p += u
    print("  data bytes=%d" % len(data))

    tmp = path + ".serialized"
    if "--out" in sys.argv:
        tmp = sys.argv[sys.argv.index("--out") + 1]
        keep = True
    else:
        keep = False
    open(tmp, "wb").write(bytes(data))
    uf = UnityFile(tmp, verbose=False)
    print("  SerializedFile objects=%d (dataOffset=%d)" % (len(uf.objects), getattr(uf, "data_offset", -1)))
    rows = [(o["classID"], o["pathID"], o["byteSize"], o["abs"]) for o in uf.objects]
    for cls in (114, 28, 21, 48):
        sel = [r for r in rows if r[0] == cls]
        if not sel:
            continue
        print("  == class %d (%s): %d 个 ==" % (cls, NAMES.get(cls, CLASS_NAMES.get(cls, "?")), len(sel)))
        for (c, pid, sz, ab) in sorted(sel, key=lambda x: -x[2])[:6]:
            print("     pathID=0x%x size=%-10d abs=%d" % (pid, sz, ab))
    # dump 指定对象 payload
    argv = sys.argv
    if "--dump" in argv:
        i = argv.index("--dump")
        cls, pid, out = int(argv[i + 1]), int(argv[i + 2], 16), argv[i + 3]
        sel = [r for r in rows if r[0] == cls and r[1] == pid]
        if not sel:
            print("  dump: not found")
        else:
            c, pid2, sz, ab = sel[0]
            buf = uf.buf[ab:ab + sz]
            open(out, "wb").write(buf)
            print("  dumped class=%d pathID=0x%x size=%d -> %s" % (cls, pid2, len(buf), out))
    if not keep:
        os.remove(tmp)
    else:
        print("  serialized kept ->", tmp)
    return 0


if __name__ == "__main__":
    sys.exit(extract(sys.argv[1]))
