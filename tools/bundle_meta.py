#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反推 bundle 的 SerializedFile 元数据段布局（数据驱动，不靠猜）：

1. 取出数据段（复用 bundle_extract 的 UnityFS + LZ4）
2. 读头：metadataSize / fileSize / version / dataOffset
3. 在元数据段 [20, 20+metadataSize) 里搜已知 classID 的**大端 4 字节模式**
   （28 Texture2D / 21 Material / 48 Shader / 114 MonoBehaviour / 115 MonoScript /
     142 AssetBundle / 49 TextAsset），打印命中偏移
4. 由命中偏移推出类型条目起始与步长 → 读 obj_n → 读对象条目（i64 pathID, u32 byteStart,
   u32 byteSize, i32 typeID），并用「对象必须落在数据段内、且尺寸包含 8192x8192 图集」验证
"""
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bundle_extract import lz4_block

CLASSES = {28: "Texture2D", 21: "Material", 48: "Shader", 114: "MonoBehaviour",
           115: "MonoScript", 142: "AssetBundle", 49: "TextAsset", 128: "Font",
           1: "GameObject", 4: "Transform", 43: "Mesh"}


def extract_data(bundle):
    d = open(bundle, "rb").read()
    p = 8 + 4
    for _ in range(2):
        p = d.index(b"\x00", p) + 1
    size, cbis, ubis, flags = struct.unpack_from(">qIII", d, p); p += 20
    bi = lz4_block(d[p:p + cbis], ubis); p += cbis
    q = 16
    cnt = struct.unpack_from(">i", bi, q)[0]; q += 4
    data = bytearray()
    for _ in range(cnt):
        u, c, f = struct.unpack_from(">IIH", bi, q); q += 10
        assert (f & 0x3F) == 0
        data += d[p:p + u]; p += u
    return bytes(data)


def main():
    sys.stdout.reconfigure(errors="backslashreplace")
    buf = extract_data(sys.argv[1])
    ms, fs, ver, do = struct.unpack_from(">IIII", buf, 0)
    print("header: metadataSize=%d fileSize=%d version=%d dataOffset=%d len=%d" % (ms, fs, ver, do, len(buf)))
    end = min(20 + ms, len(buf))
    meta = buf[20:end]
    print("metadata段长度=%d" % len(meta))

    hits = []
    for cls in sorted(CLASSES, reverse=True):
        pat = struct.pack(">I", cls)
        off = 0
        while True:
            i = meta.find(pat, off)
            if i < 0:
                break
            hits.append((20 + i, cls))
            off = i + 1
    print("classID 4 字节模式命中:")
    for (o, cls) in sorted(hits)[:40]:
        print("   @%-5d classID=%-4d %s" % (o, cls, CLASSES[cls]))
    # 猜类型条目步长：取命中偏移的差分众数
    offs = sorted(set(o for (o, _) in hits))
    diffs = {}
    for a in offs:
        for b in offs:
            d2 = b - a
            if 8 <= d2 <= 64:
                diffs[d2] = diffs.get(d2, 0) + 1
    if diffs:
        print("偏移差分频次(候选步长): %s" % sorted(diffs.items(), key=lambda x: -x[1])[:6])

    # 用候选步长试解析：类型条目起始 = 第一个命中，obj_n 紧随其后（4 字节对齐）
    for start in offs[:6]:
        for stride in [d for d, _ in sorted(diffs.items(), key=lambda x: -x[1])[:3]]:
            pos = start + 6 * stride
            for align in (0, 4):
                t = (pos + align + 3) & ~3
                if t + 4 > len(buf):
                    continue
                n = struct.unpack_from(">i", buf, t)[0]
                if not (1 <= n <= 200):
                    continue
                p = t + 4
                objs = []
                ok = True
                for _ in range(n):
                    if p + 24 > len(buf):
                        ok = False
                        break
                    pid, bs, sz, tid = struct.unpack_from(">qIIi", buf, p)
                    p += 24
                    if bs + sz > fs - do or tid < 0 or tid > 16:
                        ok = False
                        break
                    objs.append((pid, bs, sz, tid))
                if not ok or not objs:
                    continue
                sizes = [o[2] for o in objs]
                sig = 8192 * 8192 in sizes
                print(">> 试解 start=%d stride=%d obj_n@%d n=%d 含64MB图集=%s sizes=%s"
                      % (start, stride, t, n, sig, sorted(sizes, reverse=True)[:6]))
                if sig:
                    print("   对象列表:")
                    for (pid, bs, sz, tid) in sorted(objs, key=lambda x: -x[2]):
                        print("      pathID=0x%-10x typeID=%-3d size=%-10d abs=%d" % (pid, tid, sz, do + bs))
                    return 0
    print("!! 仍未定出布局；请把上面的命中偏移贴出来人工判读")
    return 2


if __name__ == "__main__":
    sys.exit(main())
