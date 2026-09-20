#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按"补丁那份字体的格式"修正我们字体资产的 FaceInfo（行距/上下缘），并顺手调材质描边。

背景（实测真值）：
  补丁字体 FaceInfo: pointSize=170, lineHeight=170.0(1.000em), ascent=146.09(0.859em),
                     descent=-23.9062(-0.141em), capLine=113.0(0.665em) ...
  我们字体 FaceInfo: pointSize=56,  lineHeight=81.088(1.448em) ... 行距宽 45%，第三行掉出对话框。
做法：把我们 FaceInfo 里 pointSize/scale 之后的 15 个 float 全部 = 补丁值 × (56/170)。

用法:
  python patch_faceinfo.py --file <in.assets> --ref <patch_backup.assets> --out <out.assets> \
      [--face-font 0xbe] [--outline-mat 0x1a] [--outline 0.08]
"""
import os, struct, sys, argparse

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
from splice_more import find_prop_float

NFLOAT = 15


def find_faceinfo(p):
    """签名: i32 pointSize(8..256) + f32 scale(0.5..2) + f32 lineHeight(0.5..3*pointSize)。"""
    for i in range(60, min(len(p) - 4 * (NFLOAT + 2), 600)):
        ps = struct.unpack_from('<i', p, i)[0]
        if not (8 <= ps <= 256):
            continue
        sc = struct.unpack_from('<f', p, i + 4)[0]
        if not (0.5 <= sc <= 2.0):
            continue
        lh = struct.unpack_from('<f', p, i + 8)[0]
        if not (0.5 * ps <= lh <= 3.0 * ps):
            continue
        return i, ps, sc
    return None, None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', required=True)
    ap.add_argument('--ref', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--face-font', default='0xbe')
    ap.add_argument('--outline-mat', default='0x1a')
    ap.add_argument('--outline', type=float, default=0.08)
    a = ap.parse_args()

    fpid = int(a.face_font, 16)
    mpid = int(a.outline_mat, 16)

    F = UnityFile(a.file, verbose=False)
    R = UnityFile(a.ref, verbose=False)

    def get(f, pid):
        o = [x for x in f.objects if (x['pathID'] & 0xFFFFFFFFFFFFFFFF) == pid]
        assert len(o) == 1, hex(pid)
        o = o[0]
        return o, f.buf[o['abs']:o['abs'] + o['byteSize']]

    of, pf = get(F, fpid)
    orf, pr = get(R, fpid)
    off_f, ps_f, sc_f = find_faceinfo(pf)
    off_r, ps_r, sc_r = find_faceinfo(pr)
    print(f'[faceinfo] ours @+{off_f} pointSize={ps_f} scale={sc_f}')
    print(f'[faceinfo] ref  @+{off_r} pointSize={ps_r} scale={sc_r}')
    assert off_f and off_r
    k = ps_f / ps_r
    print(f'[faceinfo] k = {ps_f}/{ps_r} = {k:.6f}')
    ref_vals = [struct.unpack_from('<f', pr, off_r + 8 + 4 * i)[0] for i in range(NFLOAT)]
    our_vals = [struct.unpack_from('<f', pf, off_f + 8 + 4 * i)[0] for i in range(NFLOAT)]
    new_vals = [v * k for v in ref_vals]
    for i in range(NFLOAT):
        print(f'    [{i:>2}] {our_vals[i]:>10.4f} -> {new_vals[i]:>10.4f}   (ref {ref_vals[i]:.4f})')

    buf = bytearray(F.buf)
    for i in range(NFLOAT):
        struct.pack_into('<f', buf, of['abs'] + off_f + 8 + 4 * i, new_vals[i])

    # 金币描边（Gyate 基础材质）
    om, pm = get(F, mpid)
    off_ow = find_prop_float(pm, '_OutlineWidth')
    old_ow = struct.unpack_from('<f', pm, off_ow)[0]
    struct.pack_into('<f', buf, om['abs'] + off_ow, a.outline)
    print(f'[outline] 0x{mpid:x} _OutlineWidth {old_ow:g} -> {a.outline:g}')

    struct.pack_into('>I', buf, 4, len(buf))
    open(a.out, 'wb').write(bytes(buf))

    # 独立校验
    C = UnityFile(a.out, verbose=False)
    assert len(C.objects) == len(F.objects)
    objs_same = all((x['pathID'], x['byteStart'], x['byteSize'], x['typeID']) ==
                    (y['pathID'], y['byteStart'], y['byteSize'], y['typeID'])
                    for x, y in zip(F.objects, C.objects))
    ofc, pfc = get(C, fpid)
    _, ps2, _ = find_faceinfo(pfc)
    lh2 = struct.unpack_from('<f', pfc, off_f + 8)[0]
    omc, pmc = get(C, mpid)
    ow2 = struct.unpack_from('<f', pmc, find_prop_float(pmc, '_OutlineWidth'))[0]
    # 只允许两段被改：FaceInfo 的 15 个 float 与 _OutlineWidth 的 4 字节
    ranges = sorted([(of['abs'] + off_f + 8, of['abs'] + off_f + 8 + 4 * NFLOAT),
                     (om['abs'] + off_ow, om['abs'] + off_ow + 4)])
    same = True
    prev = 0
    for s, e in ranges:
        if bytes(buf[prev:s]) != F.buf[prev:s]:
            same = False
        prev = e
    if bytes(buf[prev:]) != F.buf[prev:]:
        same = False
    print(f'[verify] objects={len(C.objects)} 对象表一致={objs_same} pointSize={ps2} '
          f'新lineHeight={lh2:g} 新_OutlineWidth={ow2:g} 只有预期字节被改={same} '
          f'fileSize头={C.file_size} 实际={len(C.buf)}')
    ok = objs_same and same and ps2 == ps_f and abs(lh2 - new_vals[0]) < 1e-4 \
        and abs(ow2 - a.outline) < 1e-6 and C.file_size == len(C.buf)
    print('RESULT:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
