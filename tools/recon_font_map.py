#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
侦察：在一个 .assets / SerializedFile 里把「TMP 字体资产 ↔ 图集 ↔ 材质」的 PPtr 关系测出来。

为什么不需要类型树：
  * MonoBehaviour 里指向自己图集/材质的 PPtr 就是 8 字节 (i32 fileID, i64 pathID)，
    而 pathID 在对象表里已知 → 直接在 payload 里搜这个 8 字节序列即可定位字段偏移。
  * Texture2D 的像素数组长度是固定的 67,108,864(8192² Alpha8)，payload 里搜这个 i32
    就知道像素起始位置。

用法: python recon_font_map.py <file.assets>
"""
import sys, os, struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile, R

CLS = {21: 'Material', 28: 'Texture2D', 48: 'Shader', 114: 'MonoBehaviour', 115: 'MonoScript'}


def try_ustr(buf, off, limit=80):
    """把 off 当作 Unity 字符串(i32 长度 + 字节)读，成功返回字符串否则 None。"""
    if off + 4 > len(buf):
        return None
    n = struct.unpack_from('<i', buf, off)[0]
    if not (1 <= n <= limit) or off + 4 + n > len(buf):
        return None
    raw = buf[off + 4:off + 4 + n]
    try:
        s = raw.decode('utf-8')
    except UnicodeDecodeError:
        return None
    if not s.isprintable():
        return None
    return s


def main():
    path = sys.argv[1]
    f = UnityFile(path, verbose=False)
    print(f'=== {os.path.basename(path)} objects={len(f.objects)} dataOffset={f.data_offset} '
          f'unity={f.unity_version!r} typeTree={f.enable_type_tree} ===')

    by_cls = {}
    for o in f.objects:
        by_cls.setdefault(o['classID'], []).append(o)

    def payload(o):
        return f.buf[o['abs']:o['abs'] + o['byteSize']]

    # --- 名字探测：class 114 取 16，28/21 取 0 与 4 都试 ---
    fonts, atlases, mats = [], [], []
    for o in by_cls.get(114, []):
        p = payload(o)
        fonts.append((o, try_ustr(p, 16) or try_ustr(p, 28) or '?'))
    for o in by_cls.get(28, []):
        p = payload(o)
        atlases.append((o, try_ustr(p, 4) or try_ustr(p, 0) or '?'))
    for o in by_cls.get(21, []):
        p = payload(o)
        mats.append((o, try_ustr(p, 4) or try_ustr(p, 0) or '?'))

    print(f'--- class 114 (MonoBehaviour) {len(fonts)} 个 ---')
    for o, nm in sorted(fonts, key=lambda x: -x[0]['byteSize']):
        print(f'   pathID_hex={o["pathID"] & 0xFFFFFFFFFFFFFFFF:016x} size={o["byteSize"]:<9} abs={o["abs"]:<9} name={nm!r}')
    print(f'--- class 28 (Texture2D) {len(atlases)} 个（只列 >=1MB）---')
    for o, nm in sorted(atlases, key=lambda x: -x[0]['byteSize']):
        if o['byteSize'] < 1024 * 1024:
            continue
        p = payload(o)
        px = -1
        for probe in (67108864, 33554432, 16777216):
            i = p.find(struct.pack('<i', probe))
            if i >= 0:
                px = (probe, i)
                break
        print(f'   pathID_hex={o["pathID"] & 0xFFFFFFFFFFFFFFFF:016x} size={o["byteSize"]:<9} abs={o["abs"]:<9} '
              f'name={nm!r} pixelArrayLen/anchor={px}')
    print(f'--- class 21 (Material) {len(mats)} 个 ---')
    for o, nm in sorted(mats, key=lambda x: x[0]['abs']):
        print(f'   pathID_hex={o["pathID"] & 0xFFFFFFFFFFFFFFFF:016x} size={o["byteSize"]:<6} abs={o["abs"]:<9} name={nm!r}')

    # --- 决定性检查：字体 payload 里搜图集/材质 pathID ---
    atlas_u64 = {o['pathID'] & 0xFFFFFFFFFFFFFFFF: nm for o, nm in atlases}
    mat_u64 = {o['pathID'] & 0xFFFFFFFFFFFFFFFF: nm for o, nm in mats}
    print('--- 字体 payload 内的 PPtr 命中（搜 8 字节 pathID）---')
    for o, nm in fonts:
        p = payload(o)
        hits = []
        for pid, tgt in list(atlas_u64.items()) + list(mat_u64.items()):
            pat = struct.pack('<Q', pid)
            start = 0
            while True:
                i = p.find(pat, start)
                if i < 0:
                    break
                file_id = struct.unpack_from('<i', p, i - 4)[0] if i >= 4 else None
                hits.append((i, tgt, file_id))
                start = i + 1
        hits.sort()
        print(f'   [{nm!r} size={o["byteSize"]}] 命中 {len(hits)} 处')
        for off, tgt, fid in hits:
            print(f'      payload+{off:<8} fileID={fid}  -> {tgt!r}')


if __name__ == '__main__':
    main()
