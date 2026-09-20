#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全量「未翻译日文」普查（所有 .assets / level* / Assembly-CSharp.dll）。

与 extract_untranslated.py 的区别：那个只看 resources.assets；这个看全部文件，
并且过滤掉：
  * 只由「・」和标点组成的串（・ 是 U+30FB，落在片假名区，会误报）
  * Unity/程序内部串（含 "UnityEngine"/"System."/", Version=" 等）
  * 字体资产对象（class 114 且 byteSize > 100000）

输出：_hanhua/out/untranslated_all.csv + 控制台分组统计
"""
import collections
import csv
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
from netmeta import PE, parse_us

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DATA = os.path.join(ROOT, "kotonoha_Data")
OUT = os.path.join(ROOT, "_hanhua", "out", "untranslated_all.csv")

KANA = re.compile(r"[\u3041-\u309F\u30A1-\u30FA\u30FC-\u30FF]")   # 真假名（不含・U+30FB）
SYSTEMISH = re.compile(r"UnityEngine|System\.|, Version=|mscorlib|Assembly-CSharp|\.dll|\[CN\]")


def unity_strings(raw, lo=2, hi=2000):
    out = []
    i = 0
    n = len(raw)
    while i + 4 <= n:
        L = struct.unpack_from("<i", raw, i)[0]
        if lo <= L <= hi and i + 4 + L <= n:
            bs = raw[i + 4:i + 4 + L]
            if b"\x00" not in bs:
                try:
                    s = bs.decode("utf-8")
                except UnicodeDecodeError:
                    i += 1
                    continue
                out.append((i + 4, L, s))
                i += 4 + L
                i = (i + 3) & ~3
                continue
        i += 1
    return out


def main():
    sys.stdout.reconfigure(errors="backslashreplace")
    files = [f for f in sorted(os.listdir(DATA))
             if f.endswith(".assets") or (f.startswith("level") and "." not in f)]
    rows = []
    per_file = collections.Counter()
    for fname in files:
        p = os.path.join(DATA, fname)
        if not os.path.exists(p):
            continue
        try:
            uf = UnityFile(p, verbose=False)
        except Exception:
            continue
        for o in uf.objects:
            if o["classID"] not in (49, 114):
                continue
            if o["classID"] == 114 and o["byteSize"] > 100000:
                continue          # 字体资产里的伪命中
            raw = uf.buf[o["abs"]:o["abs"] + o["byteSize"]]
            if not raw:
                continue
            try:
                strs = unity_strings(raw)
            except Exception:
                continue
            for off, L, s in strs:
                if not KANA.search(s):
                    continue
                if SYSTEMISH.search(s):
                    continue
                rows.append({
                    "file": fname, "cls": o["classID"], "pathID": "0x%x" % o["pathID"],
                    "objAbs": o["abs"], "strOff": o["abs"] + off, "length": L,
                    "text": s,
                })
                per_file[fname] += 1
    # DLL
    dll = os.path.join(DATA, "Managed", "Assembly-CSharp.dll")
    if os.path.exists(dll):
        for s in parse_us(PE(dll)):
            if KANA.search(s) and not SYSTEMISH.search(s):
                rows.append({"file": "Assembly-CSharp.dll", "cls": 0, "pathID": "-",
                             "objAbs": 0, "strOff": 0, "length": len(s.encode("utf-8")), "text": s})
                per_file["Assembly-CSharp.dll"] += 1

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "cls", "pathID", "objAbs", "strOff", "length", "text"])
        w.writeheader()
        w.writerows(rows)

    print("=== 未翻译日文总计: %d 条 ===" % len(rows))
    for f, n in per_file.most_common():
        print("  %-26s %d" % (f, n))
    print("清单 -> " + OUT)
    print("=== 前 60 条 ===")
    for r in rows[:60]:
        body = r["text"].replace("\n", "\\n")
        if len(body) > 110:
            body = body[:110] + "…"
        print("  %s %s %s @%s L=%s\n     %s" % (r["file"], r["cls"], r["pathID"], r["strOff"], r["length"],
                                                body.encode("ascii", "backslashreplace").decode()))


if __name__ == "__main__":
    main()
