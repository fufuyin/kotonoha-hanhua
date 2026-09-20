#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验收脚本：把 Unity creator 流程烤出来的 creator_report.tsv 与「补丁真正用到的字符集」逐码位比对。

needed = EXTRA(ASCII+全角+常用标点) ∪ patch_texts ∪ scan(补丁 resources/sharedassets0/level*)
         ∪ Assembly-CSharp.dll 的 #US 字符串
  -> 这是「游戏里真的会出现」的字符集，不含 bake_charset 里由 detect_runs 启发式带来的噪声。

用法: python verify_bake.py <补丁目录> [--report <creator_report.tsv>]
"""
import argparse
import collections
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_coverage_all import scan_asset_strings
from netmeta import PE, parse_us

DEFAULT_REPORT = r"F:\Application\Unity\creator_report.tsv"

EXTRA = set()
for a in range(0x20, 0x7F):
    EXTRA.add(a)
for a in range(0xFF01, 0xFF5F):
    EXTRA.add(a)
for a in (0x3000, 0x3001, 0x3002, 0x300C, 0x300D, 0x300E, 0x300F, 0x3010, 0x3011,
          0x301C, 0x301D, 0x301F, 0x30FB, 0x30FC, 0x2015, 0x2018, 0x2019, 0x201C,
          0x201D, 0x2026, 0x2010, 0x00B7, 0x00A5, 0x203B, 0x3013, 0x3231, 0x3232,
          0x3239, 0x32A4, 0x32A5, 0x32A6, 0x32A7, 0x32A8, 0x33A1, 0x337B, 0x33CD):
    EXTRA.add(a)


def read_report(path):
    status = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            f2 = line.rstrip("\n").split("\t")
            if len(f2) < 12 or not f2[0].startswith("U+"):
                continue
            try:
                cp = int(f2[0][2:], 16)
            except ValueError:
                continue
            status[cp] = f2[11]
    return status


def needed_set(patch_dir, outdir):
    d = collections.OrderedDict()
    d["EXTRA(固定标点/ASCII/全角)"] = set(EXTRA)

    pt = set()
    for p in glob.glob(os.path.join(outdir, "patch_texts", "*.txt")):
        pt |= {ord(c) for c in open(p, encoding="utf-8", errors="ignore").read()}
    d["patch_texts 译文"] = pt

    ui = set()
    for name in ("resources.assets", "sharedassets0.assets"):
        p = os.path.join(patch_dir, name)
        if os.path.exists(p):
            ui |= {ord(c) for c in scan_asset_strings(p)}
    d["resources/sharedassets0 UI"] = ui

    lv = set()
    files = [os.path.join(patch_dir, f) for f in os.listdir(patch_dir)
             if f.startswith("level") and "." not in f]
    for p in sorted(files):
        lv |= {ord(c) for c in scan_asset_strings(p)}
    d["level 场景"] = lv

    dll = set()
    dp = os.path.join(patch_dir, "Managed", "Assembly-CSharp.dll")
    if os.path.exists(dp):
        pe = PE(dp)
        for s in parse_us(pe):
            dll |= {ord(c) for c in s if ord(c) >= 0x20}
    d["Assembly-CSharp.dll 字符串"] = dll
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("patch_dir")
    ap.add_argument("--report", default=DEFAULT_REPORT)
    ap.add_argument("--outdir", default="_hanhua/out")
    a = ap.parse_args()
    sys.stdout.reconfigure(errors="backslashreplace")

    if not os.path.exists(a.report):
        print("report not found: " + a.report)
        return 1

    status = read_report(a.report)
    ok = {cp for cp, s in status.items() if s == "ok"}
    empty = {cp for cp, s in status.items() if s == "emptyRect"}
    noidx = {cp for cp, s in status.items() if s == "noGlyphIndex"}
    notpacked = {cp for cp, s in status.items() if s == "notPacked"}
    print("report: entries=%d ok=%d emptyRect=%d noGlyphIndex=%d notPacked=%d"
          % (len(status), len(ok), len(empty), len(noidx), len(notpacked)))

    d = needed_set(a.patch_dir, a.outdir)
    allneed = set()
    print()
    for k, v in d.items():
        allneed |= v
        miss = sorted(v - ok)
        print("  %-28s 需要 %-5d 缺 %-5d" % (k, len(v), len(miss)))
    allneed = {c for c in allneed if c >= 0x20 and not (0xD800 <= c <= 0xDFFF)}
    miss = sorted(allneed - ok)
    print()
    print("===> 全量：真正需要 %d 个码位，字体已渲染 %d，缺 %d"
          % (len(allneed), len(allneed & ok), len(miss)))
    sym = [c for c in miss if not (0x4E00 <= c <= 0x9FFF)]
    han = [c for c in miss if 0x4E00 <= c <= 0x9FFF]
    print("     其中汉字 %d，符号/假名 %d" % (len(han), len(sym)))
    if han:
        print("     缺汉字: " + "".join(chr(c) for c in han).encode("ascii", "backslashreplace").decode())
    if sym:
        print("     缺符号: " + "".join(chr(c) for c in sym).encode("ascii", "backslashreplace").decode())

    out = os.path.join(a.outdir, "verify_bake_missing.txt")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("".join(chr(c) for c in miss))
    print("     清单 -> " + out)

    # the 17 chars that the old TMP TryAddCharacters path dropped
    probe = [0x00B0, 0x00B7, 0x00BB, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D,
             0x2020, 0x2021, 0x2025, 0x2026, 0x203C, 0x2047, 0x2048, 0x2049, 0x2103]
    print()
    print("旧路径丢掉的 17 个关键符号，本次结果:")
    for cp in probe:
        print("   U+%04X %-4s" % (cp, status.get(cp, "NOT-IN-REPORT")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
