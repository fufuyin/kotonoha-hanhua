#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按 pathID 对齐两个文件里的 Material，逐属性打印差异（用于判断补丁作者改了哪些材质数值）。

用法: python diff_materials.py <A.assets> <B.assets> [--filter SDF]
  A = 基准（原版未打补丁），B = 对比（补丁/我们改过的）
"""
import os, sys, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
from probe_mat_props import scan_props, read_ustr


def mats(path):
    f = UnityFile(path, verbose=False)
    out = {}
    for o in f.objects:
        if o['classID'] != 21:
            continue
        p = f.buf[o['abs']:o['abs'] + o['byteSize']]
        name = '?'
        for off in (0, 4):
            r = read_ustr(p, off, lo=1, hi=80)
            if r:
                name = r[0]
                break
        fl, co = scan_props(p)
        out[o['pathID'] & 0xFFFFFFFFFFFFFFFF] = (name, fl, co)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('a')
    ap.add_argument('b')
    ap.add_argument('--filter', default=None)
    a = ap.parse_args()
    A, B = mats(a.a), mats(a.b)
    print(f'A={os.path.basename(a.a)} ({len(A)} materials)   B={os.path.basename(a.b)} ({len(B)} materials)')
    ndiff = 0
    for pid in sorted(A):
        n1, f1, c1 = A[pid]
        if a.filter and a.filter.lower() not in n1.lower():
            continue
        if pid not in B:
            print(f'!! {n1} (0x{pid:x}) 在 B 中不存在')
            continue
        n2, f2, c2 = B[pid]
        df = {k: (f1.get(k), f2.get(k)) for k in set(f1) | set(f2)
              if abs((f1.get(k) if f1.get(k) is not None else 0) - (f2.get(k) if f2.get(k) is not None else 0)) > 1e-6}
        dc = {k: (c1.get(k), c2.get(k)) for k in set(c1) | set(c2) if c1.get(k) != c2.get(k)}
        if df or dc:
            ndiff += 1
            print(f'--- {n1} (0x{pid:x})  name: {n1} -> {n2}')
            for k, (x, y) in sorted(df.items()):
                print(f'    {k}: {x} -> {y}')
            for k, (x, y) in sorted(dc.items()):
                print(f'    {k}: {x} -> {y}')
    print(f'=> 有差异的材质 {ndiff} 个')


if __name__ == '__main__':
    main()
