#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按名字子串在 .assets 里找对象（Material / Texture2D / MonoBehaviour / TextAsset / Shader）。

名字偏移实测：Texture2D/Material 在 0；MonoBehaviour 在 16；TextAsset 在 0。
用法: python find_named.py <file> <substring> [--class 21,28,114]
"""
import os, struct, sys, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
from probe_mat_props import read_ustr

OFFS = {21: (0, 4), 28: (0, 4), 48: (0, 4), 49: (0,), 114: (16, 28)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('needle')
    ap.add_argument('--class', dest='classes', default='21,28,114,48,49')
    a = ap.parse_args()
    classes = {int(x) for x in a.classes.split(',') if x.strip()}
    f = UnityFile(a.path, verbose=False)
    print(f'=== {os.path.basename(a.path)} objects={len(f.objects)} 查找 {a.needle!r} ===')
    hits = 0
    for o in f.objects:
        if o['classID'] not in classes:
            continue
        p = f.buf[o['abs']:o['abs'] + o['byteSize']]
        name = None
        for off in OFFS.get(o['classID'], (0,)):
            r = read_ustr(p, off, lo=1, hi=120)
            if r:
                name = r[0]
                break
        if name and a.needle.lower() in name.lower():
            hits += 1
            print(f'  class={o["classID"]:>3} pathID=0x{o["pathID"] & 0xFFFFFFFFFFFFFFFF:016x} '
                  f'size={o["byteSize"]:<10} abs={o["abs"]:<10} name={name!r}')
    print(f'=> 命中 {hits} 个')


if __name__ == '__main__':
    main()
