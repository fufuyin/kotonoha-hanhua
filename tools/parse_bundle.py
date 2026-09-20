#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取「未压缩的 AssetBundle」(UnityFS)，把它里面的 SerializedFile 解出来交给 unityfile 解析，
用来定位我们烤出来的字体资产（class 114 MonoBehaviour）、图集纹理（class 28）、材质（class 21）
各自的 pathID 与 payload 大小 —— 这是把资源移植进游戏 .assets 的前提。

用法: python parse_bundle.py <bundle 文件>
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile, CLASS_NAMES

NAMES = {21: "Material", 28: "Texture2D", 48: "Shader", 114: "MonoBehaviour", 115: "MonoScript", 142: "AssetBundle"}


def main():
    path = sys.argv[1]
    d = open(path, "rb").read()
    print("bundle=%s bytes=%d" % (os.path.basename(path), len(d)))
    assert d[:8] == b"UnityFS\x00", "not UnityFS"
    p = 8
    version = struct.unpack_from(">i", d, p)[0]; p += 4
    for _ in range(2):                       # unityVersion + unityRevision (two null-terminated strings!)
        end = d.index(b"\x00", p)
        _s = d[p:end].decode("latin-1"); p = end + 1
        if _ == 0:
            unity_ver = _s
        else:
            unity_rev = _s
    size, cbis, ubis, flags = struct.unpack_from(">qIII", d, p); p += 20
    comp = flags & 0x3F
    print("  version=%d unity=%s rev=%s size=%d compressedBlocksInfo=%d uncompressedBlocksInfo=%d flags=0x%x comp=%d"
          % (version, unity_ver, unity_rev, size, cbis, ubis, flags, comp))
    assert comp == 0, "bundle 不是未压缩（comp=%d），请用 UncompressedAssetBundle 重新打包" % comp

    # blocksInfo: u32 uncompressedSize, u32 compressedSize, u16 flags
    ub, cb, bf = struct.unpack_from(">IIH", d, p); p += 10
    nblocks = ub // 10
    blocks = []
    if nblocks > 0:
        for i in range(nblocks):
            u, c, f = struct.unpack_from(">IIH", d, p); p += 10
            blocks.append((u, c, f))
    print("  blocksInfo: first(u=%d c=%d f=0x%x) blocks=%d" % (ub, cb, bf, nblocks))
    # data: 未压缩 -> 顺序拼接
    data = bytearray()
    for (u, c, f) in blocks:
        data += d[p:p + u]
        p += u
    print("  data bytes=%d" % len(data))

    tmp = path + ".serialized"
    open(tmp, "wb").write(bytes(data))
    uf = UnityFile(tmp, verbose=False)
    print("  SerializedFile objects=%d" % len(uf.objects))
    rows = []
    for o in uf.objects:
        rows.append((o["classID"], o["pathID"], o["byteSize"], o["abs"]))
    for cls in (114, 28, 21, 48):
        sel = [r for r in rows if r[0] == cls]
        if not sel:
            continue
        print("  == class %d (%s) : %d 个 ==" % (cls, NAMES.get(cls, CLASS_NAMES.get(cls, "?")), len(sel)))
        for (c, pid, sz, ab) in sorted(sel, key=lambda x: -x[2])[:6]:
            print("     pathID=0x%x size=%-10d abs=%d" % (pid, sz, ab))
    os.remove(tmp)


if __name__ == "__main__":
    main()
