#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单点材质数值修补：只改指定 Material 的一个 float 属性，其余字节逐字节保持不变。

用法:
  python patch_mat_float.py --file <in.assets> --out <out.assets> --pathid 0x1a \
      --prop _OutlineWidth --value 0.15 [--verify-only]
"""
import os, struct, sys, argparse, hashlib

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
from splice_more import find_prop_float


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', required=True)
    ap.add_argument('--out', default=None)
    ap.add_argument('--pathid', required=True)
    ap.add_argument('--prop', required=True)
    ap.add_argument('--value', type=float, required=True)
    a = ap.parse_args()

    pid = int(a.pathid, 16)
    f = UnityFile(a.file, verbose=False)
    o = [x for x in f.objects if (x['pathID'] & 0xFFFFFFFFFFFFFFFF) == pid]
    assert len(o) == 1, f'找不到唯一对象 {hex(pid)}'
    o = o[0]
    p = f.buf[o['abs']:o['abs'] + o['byteSize']]
    off = find_prop_float(p, a.prop)
    assert off is not None, f'对象里找不到属性 {a.prop}'
    old = struct.unpack_from('<f', p, off)[0]
    print(f'[mat] 0x{pid:x} {a.prop}: {old:g} -> {a.value:g}  (payload+{off}, abs={o["abs"] + off})')

    buf = bytearray(f.buf)
    struct.pack_into('<f', buf, o['abs'] + off, a.value)
    struct.pack_into('>I', buf, 4, len(buf))

    if a.out:
        open(a.out, 'wb').write(bytes(buf))
        print(f'[out] {a.out} ({len(buf)} bytes)')

    # 独立校验：重新解析写出文件，逐字节比对（只允许那 4 字节不同）
    chk = UnityFile(a.out, verbose=False) if a.out else None
    if chk:
        assert len(chk.objects) == len(f.objects)
        diff = []
        oo = [x for x in chk.objects if (x['pathID'] & 0xFFFFFFFFFFFFFFFF) == pid][0]
        pp = chk.buf[oo['abs']:oo['abs'] + oo['byteSize']]
        newv = struct.unpack_from('<f', pp, off)[0]
        same_prefix = chk.buf[:oo['abs'] + off] == f.buf[:o['abs'] + off]
        tail_start = o['abs'] + off + 4
        same_tail = chk.buf[tail_start:] == f.buf[tail_start:]
        # 对象表/其它对象
        objs_same = all(
            (xa['pathID'], xa['byteStart'], xa['byteSize'], xa['typeID']) ==
            (xb['pathID'], xb['byteStart'], xb['byteSize'], xb['typeID'])
            for xa, xb in zip(f.objects, chk.objects))
        print(f'[verify] objects={len(chk.objects)} 对象表一致={objs_same} '
              f'前缀一致={same_prefix} 后缀一致={same_tail} 新值={newv:g} '
              f'fileSize头={chk.file_size} 实际={len(chk.buf)}')
        ok = objs_same and same_prefix and same_tail and abs(newv - a.value) < 1e-5 \
            and chk.file_size == len(chk.buf)
        print('RESULT:', 'PASS' if ok else 'FAIL')
        return 0 if ok else 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
