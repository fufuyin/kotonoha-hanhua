#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare candidate source fonts by cmap coverage over the data sets that matter:
  * bake charset          (out/bake_charset.txt, 8658)
  * real patch text       (out/patch_texts/*.txt)
  * the 74 cps Unity refused  (out/baked_missing_present_in_font.txt)
Also reports the refused-74 coverage, which is the whole point.
"""
import glob
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from otf_cmap import Sfnt

OUT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out"))

CANDIDATES = [
    r"F:\Application\Unity\fonts\NotoSansCJKsc-Regular.otf",
    r"C:\Windows\Fonts\NotoSansSC-VF.ttf",
    r"C:\Windows\Fonts\NotoSansJP-VF.ttf",
    r"C:\Windows\Fonts\Deng.ttf",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simkai.ttf",
    r"C:\Windows\Fonts\STXIHEI.TTF",
    r"C:\Windows\Fonts\yumin.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\seguisym.ttf",
]


def load_sets():
    charset = io.open(os.path.join(OUT, "bake_charset.txt"), encoding="utf-8").read()
    cs = {ord(c) for c in charset}
    pt = set()
    for p in glob.glob(os.path.join(OUT, "patch_texts", "*.txt")):
        pt |= {ord(c) for c in io.open(p, encoding="utf-8", errors="ignore").read()}
    ref = io.open(os.path.join(OUT, "baked_missing_present_in_font.txt"), encoding="utf-8").read()
    rf = {ord(c) for c in ref}
    return cs, pt, rf


def main():
    sys.stdout.reconfigure(errors="backslashreplace")
    cs, pt, rf = load_sets()
    print("datasets: charset=%d  patch_texts=%d  refused74=%d" % (len(cs), len(pt), len(rf)))
    for path in CANDIDATES:
        if not os.path.exists(path):
            print("\n%-58s MISSING FILE" % os.path.basename(path))
            continue
        try:
            f = Sfnt(path)
        except Exception as e:
            print("\n%-58s PARSE FAIL %r" % (os.path.basename(path), e))
            continue
        mapped = set(f.cmap.keys())
        print("\n%-58s mapped=%d flavor=%s" % (os.path.basename(path), len(mapped), f.flavor))
        for name, s in (("charset(8658)", cs), ("patch_texts", pt), ("refused74", rf)):
            miss = s - mapped
            extra = ""
            if name == "refused74" and not miss:
                extra = "   <-- covers ALL refused symbols"
            print("   %-14s missing=%-5d%s" % (name, len(miss), extra))
        miss74 = sorted(rf - mapped)
        # the actionable set for a CJK+symbol font: patch text chars
        mt = sorted(pt - mapped)
        if mt:
            print("   patch-text chars NOT in this font (%d): %s"
                  % (len(mt), "".join(chr(c) for c in mt[:200]).encode("ascii", "backslashreplace").decode()))
        if miss74:
            print("   refused-74 not in this font: %s"
                  % "".join(chr(c) for c in miss74).encode("ascii", "backslashreplace").decode())


if __name__ == "__main__":
    main()
