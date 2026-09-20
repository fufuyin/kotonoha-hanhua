#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比「原补丁 alpha1.2」与「未改动的本体备份」，看它到底对字体做了什么：
  - 文件大小、对象数量（判断是"追加对象"还是"原地替换"）
  - 每支 Texture2D（名字/尺寸/格式/对象大小）—— 看它加/换了哪些图集
  - class 114 且 >100KB 的对象（TMP 字体资产）数量与大小
用法: python compare_patch_fonts.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile, R

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ORIG = os.path.join(ROOT, "_hanhua", "backup", "original")
PATCH = r"D:\桌面\补丁alpha1.2-放在kotonoha_Data下"
FORMATS = {1: "Alpha8", 4: "RGBA32", 5: "ARGB32", 10: "DXT1", 12: "DXT5", 14: "BGRA32"}


def tex_info(f, o):
    r = R(f.buf, o["abs"])
    name = r.ustr().decode("utf-8", "replace")
    r.i32(); r.bool(); r.bool(); r.align(4)
    w = r.i32(); h = r.i32(); cis = r.u32(); fmt = r.i32()
    return name, w, h, FORMATS.get(fmt, fmt), cis


def report(label, path):
    if not os.path.exists(path):
        print("  %-22s MISSING %s" % (label, path))
        return
    print("  %-22s size=%d" % (label, os.path.getsize(path)))
    try:
        f = UnityFile(path, verbose=False)
    except Exception as e:
        print("      parse failed: %r" % (e,))
        return
    print("      objects=%d" % len(f.objects))
    tex = []
    big = []
    for o in f.objects:
        if o["classID"] == 28:
            try:
                tex.append((tex_info(f, o), o["byteSize"]))
            except Exception:
                pass
        elif o["classID"] == 114 and o["byteSize"] > 100000:
            big.append(o["byteSize"])
    print("      Texture2D=%d ; class114(>100KB, 字体类)=%d sizes=%s"
          % (len(tex), len(big), sorted(big, reverse=True)[:6]))
    for (t, sz) in sorted(tex, key=lambda x: -x[1])[:6]:
        print("        tex %-34s %5dx%-5d %-8s cis=%-9d objSize=%d" % (t[0], t[1], t[2], t[3], t[4], sz))


def main():
    sys.stdout.reconfigure(errors="backslashreplace")
    for fn in ("resources.assets", "sharedassets0.assets"):
        print("=== %s ===" % fn)
        report("本体(未改动)", os.path.join(ORIG, fn))
        report("原补丁 alpha1.2", os.path.join(PATCH, fn))
        print("")


if __name__ == "__main__":
    main()
