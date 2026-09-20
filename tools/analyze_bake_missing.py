#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-check the code points that the Unity bake could NOT add against the
source font's own cmap, to separate:
  (A) really absent from the font file  -> the charset was polluted, ignore
  (B) present in the font file          -> Unity's FontEngine refused it, bug/limitation
Also dumps each cmap subtable's coverage of group (B).
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from otf_cmap import Sfnt

OTF = r"F:\Application\Unity\fonts\NotoSansCJKsc-Regular.otf"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out")


def main():
    f = Sfnt(OTF)
    missing = io.open(os.path.join(OUT, "baked_missing.txt"), encoding="utf-8").read()
    cps = sorted({ord(c) for c in missing})
    print("missing code points = %d" % len(cps))

    present = [c for c in cps if f.has(c)]
    absent = [c for c in cps if not f.has(c)]
    print("  (B) present in OTF but refused by Unity : %d" % len(present))
    print("  (A) really absent from OTF              : %d" % len(absent))

    def bucket(lst):
        b = {}
        for c in lst:
            b[c >> 8] = b.get(c >> 8, 0) + 1
        return b

    print("  (B) by plane: " + ", ".join("U+%02Xxx=%d" % (k, v) for k, v in sorted(bucket(present).items())))
    print("  (A) by plane: " + ", ".join("U+%02Xxx=%d" % (k, v) for k, v in sorted(bucket(absent).items())))

    print("  (B) sample: " + "".join(chr(c) for c in present[:120]).encode("ascii", "backslashreplace").decode())
    print("  (A) sample: " + "".join(chr(c) for c in absent[:120]).encode("ascii", "backslashreplace").decode())

    # per-subtable coverage
    print("\ncmap subtables of the source font:")
    sets = []
    for pid, eid, fmt, m in f.all_cmaps():
        sets.append(((pid, eid, fmt), m))
        npres = sum(1 for c in present if c in m)
        print("  (pid=%d,eid=%d,fmt=%d) mapped=%d  covers %d/%d of group B"
              % (pid, eid, fmt, len(m), npres, len(present)))

    # is group B == everything covered by fmt12 but NOT by fmt4?
    print("\nhypothesis: group B == fmt12-only characters")
    for key, m in sets:
        only = [c for c in present if c not in m]
        print("  not in %s : %d" % (key, len(only)))

    # which real source (patch text / scanned assets) chars are in group B?
    pt = os.path.join(OUT, "patch_texts")
    realset = set()
    if os.path.isdir(pt):
        import glob
        for p in glob.glob(os.path.join(pt, "*.txt")):
            realset |= {ord(c) for c in io.open(p, encoding="utf-8", errors="ignore").read()}
    print("\npatch_texts distinct chars = %d" % len(realset))
    inter = sorted(realset & set(cps))
    print("patch_texts chars that the bake MISSED = %d" % len(inter))
    if inter:
        s = "".join(chr(c) for c in inter)
        print("  " + s.encode("ascii", "backslashreplace").decode())

    # write group B for the next experiment
    with io.open(os.path.join(OUT, "baked_missing_present_in_font.txt"), "w", encoding="utf-8") as fh:
        fh.write("".join(chr(c) for c in present))
    with io.open(os.path.join(OUT, "baked_missing_absent_in_font.txt"), "w", encoding="utf-8") as fh:
        fh.write("".join(chr(c) for c in absent))
    print("\nwrote baked_missing_present_in_font.txt / baked_missing_absent_in_font.txt")


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="backslashreplace")
    main()
