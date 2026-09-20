#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 verify_bake 报的缺字逐个归因：真译文 / DLL 字符串 / 原始字节扫描噪声。"""
import glob
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from netmeta import PE, parse_us

GAME = r"F:\Steam\steamapps\common\琴葉姉妹とライサント島の伝説\kotonoha\kotonoha_Data"
OUT = r"F:\Steam\steamapps\common\琴葉姉妹とライサント島の伝説\kotonoha\_hanhua\out"
CHARSET = r"F:\Application\Unity\charset.txt"
REPORT = r"F:\Application\Unity\creator_report.tsv"


def main():
    sys.stdout.reconfigure(errors="backslashreplace")
    missing = io.open(os.path.join(OUT, "verify_bake_missing.txt"), encoding="utf-8").read()
    miss = [ord(c) for c in missing]
    print("missing set = %d" % len(miss))

    pt = set()
    for p in glob.glob(os.path.join(OUT, "patch_texts", "*.txt")):
        pt |= {ord(c) for c in io.open(p, encoding="utf-8", errors="ignore").read()}
    dll = set()
    pe = PE(os.path.join(GAME, "Managed", "Assembly-CSharp.dll"))
    for s in parse_us(pe):
        dll |= {ord(c) for c in s if ord(c) >= 0x20}
    charset = io.open(CHARSET, encoding="utf-8").read()
    cs = {ord(c) for c in charset}
    report = set()
    for line in io.open(REPORT, encoding="utf-8").read().splitlines():
        if line.startswith("U+"):
            report.add(int(line[2:6], 16))

    print("\n%-8s %-8s %-8s %-8s %-8s  %s" % ("cp", "patchtxt", "dll", "charset", "inreport", "raw"))
    for cp in sorted(miss):
        row = []
        for s in (pt, dll, cs, report):
            row.append("YES" if cp in s else "-")
        raw = "".join(chr(cp)).encode("ascii", "backslashreplace").decode()
        print("U+%04X  %-8s %-8s %-8s %-8s  %s" % (cp, row[0], row[1], row[2], row[3], raw))

    only_pt = sorted(set(miss) & pt)
    print("\n真正出现在译文里的缺字 = %d : %s"
          % (len(only_pt), "".join(chr(c) for c in only_pt).encode("ascii", "backslashreplace").decode()))


if __name__ == "__main__":
    main()
