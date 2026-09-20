#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校验"全字体资产化"这批改动（sharedassets0）：
  * 对象数与身份不变；除白名单外所有对象逐字节一致
  * 0xbf/0xc0/0xc1 三个字体：名字/m_Script 保留、atlas/material PPtr 正确、无我们 bundle 的 pathID
  * 0x52/0x53 图集像素 == 黄金像素；0x1e/0x1f 图集像素未动
  * 9 个 Rii/Stick 材质：_MainTex 已指向 0x53，旧图集引用（fileID=0）已消失

用法: python verify_allfonts.py --orig <装之前的文件> --out <新文件> --our <our_simhei.serialized>
"""
import os, sys, struct, argparse, hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from unityfile import UnityFile
from splice_fonts import find_pixels, find_pptr, parse_head, obj_payload
from splice_more import find_prop_float

PIX = 8192 * 8192
FONTS = {0xbf: ('Makinas-4-Square SDF', 0x52, 0x1b),
         0xc0: ('RiiPopkkR SDF', 0x53, 0x1c),
         0xc1: ('Stick_Regular SDF', 0x53, 0x1d)}
MATS = [0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x1c, 0x1d]
ATLAS_CHANGED = {0x52, 0x53}
MAT_PATCHED = set(MATS) | {0x1a, 0x52, 0x53}
WHITELIST = set(FONTS) | MAT_PATCHED


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--orig', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--our', required=True)
    ap.add_argument('--golden', default=r'F:\Application\Unity\twobake_atlas.bin')
    a = ap.parse_args()
    ok = True

    A = UnityFile(a.orig, verbose=False)
    B = UnityFile(a.out, verbose=False)
    O = UnityFile(a.our, verbose=False)
    ours_all = {o['pathID'] & 0xFFFFFFFFFFFFFFFF for o in O.objects}

    print(f'[1] objects {len(A.objects)} -> {len(B.objects)}')
    if len(A.objects) != len(B.objects):
        print('    !! 对象数不一致'); ok = False

    bmap = {o['pathID']: o for o in B.objects}
    changed = []
    for oa in A.objects:
        pid = oa['pathID'] & 0xFFFFFFFFFFFFFFFF
        ob = bmap.get(oa['pathID'])
        if ob is None or (oa['byteStart'], oa['byteSize']) != (ob['byteStart'], ob['byteSize']):
            changed.append(pid)
            continue
        if obj_payload(A, oa) != obj_payload(B, ob):
            changed.append(pid)
    unexpected = [hex(p) for p in changed if p not in WHITELIST]
    print(f'[2] 变化的对象 {len(changed)} 个: {[hex(p) for p in sorted(changed)]}')
    if unexpected:
        print(f'    !! 白名单外还有变化: {unexpected}'); ok = False

    print('[3] 字体对象:')
    for pid, (name, apid, mpid) in FONTS.items():
        ob = bmap.get(pid)
        pb = obj_payload(B, ob)
        nm, ne, sc = parse_head(pb)
        oa = [x for x in A.objects if (x['pathID'] & 0xFFFFFFFFFFFFFFFF) == pid][0]
        pa = obj_payload(A, oa)
        hits_a = [h for h in find_pptr(pb, apid) if h[1] == 0]
        hits_m = [h for h in find_pptr(pb, mpid) if h[1] == 0]
        left = {hex(p): len(find_pptr(pb, p)) for p in ours_all
                if p >= 0x1000 and find_pptr(pb, p)}
        good = (nm == name and pb[12] == 1 and pb[16:28] == pa[16:28]
                and hits_a and hits_m and not left)
        print(f'    {"OK " if good else "!! "}0x{pid:x} {nm!r} size={ob["byteSize"]} '
              f'atlas_hit={len(hits_a)} mat_hit={len(hits_m)} 自家残留={left or "无"}')
        ok = ok and good

    print('[4] 图集像素:')
    golden = open(a.golden, 'rb').read() if os.path.exists(a.golden) else None
    for pid in (0x1e, 0x1f, 0x52, 0x53):
        ob = bmap.get(pid)
        if ob is None:
            print(f'    !! 缺少图集 0x{pid:x}'); ok = False; continue
        pb = obj_payload(B, ob)
        po, _ = find_pixels(pb)
        if po is None:
            print(f'    0x{pid:x} 尺寸 {ob["byteSize"]}（非 8192²，跳过像素比对）')
            continue
        px = pb[po:po + PIX]
        if pid in ATLAS_CHANGED:
            same = (golden is not None and px == golden)
            print(f'    {"OK " if same else "!! "}0x{pid:x} 像素 == 黄金: {same}')
            ok = ok and same
        else:
            oa = [x for x in A.objects if (x['pathID'] & 0xFFFFFFFFFFFFFFFF) == pid]
            if oa:
                pa = obj_payload(A, oa[0])
                pao, _ = find_pixels(pa)
                same = (pao == po and pa[pao:pao + PIX] == px)
                print(f'    {"OK " if same else "!! "}0x{pid:x} 像素未变: {same}')
                ok = ok and same

    print('[5] 材质重定向:')
    old_ids = {0x1e: 'Stick', 0x1f: 'Rii'}
    for pid in MATS:
        ob = bmap.get(pid)
        pb = obj_payload(B, ob)
        oa = [x for x in A.objects if (x['pathID'] & 0xFFFFFFFFFFFFFFFF) == pid][0]
        pa = obj_payload(A, oa)
        old_hits = []
        for oid in old_ids:
            old_hits += [h for h in find_pptr(pa, oid) if h[1] == 0]
        new_hits = [h for h in find_pptr(pb, 0x53) if h[1] == 0]
        gs_off = find_prop_float(pb, '_GradientScale')
        gs = struct.unpack_from('<f', pb, gs_off)[0] if gs_off is not None else -1
        good = (bool(old_hits) and new_hits and abs(gs - 11.0) < 1e-4)
        print(f'    {"OK " if good else "!! "}0x{pid:x} 旧图集引用={len(old_hits)} -> 新引用={len(new_hits)} '
              f'_GradientScale={gs:g}')
        ok = ok and good

    print('RESULT:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
