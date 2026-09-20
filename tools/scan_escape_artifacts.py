#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描游戏文本里的「转义残留垃圾」：前一位译者把 \\u3000 / \\n 之类的转义写成了字面量，
玩家会在对话框/道具说明里直接看到 "u3000"、"\n" 这种东西。

覆盖来源：
  * TextAsset（台词）字符串
  * MonoBehaviour 字符串（UI/道具说明）
  * Assembly-CSharp.dll 的 #US 字符串
报告：文件 / 类 / pathID / 偏移 / 前后文，按模式分组统计。
不写盘（只读）。
"""
import collections
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
from netmeta import PE, parse_us

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DATA = os.path.join(ROOT, "kotonoha_Data")

PATTERNS = [
    ("u3000", re.compile(r"u3000")),
    ("backslash_u", re.compile(r"\\u[0-9a-fA-F]{4}")),
    ("literal_backslash_n", re.compile(r"\\n")),
    ("dollar_brace", re.compile(r"\$\{")),
]


def unity_strings(raw, lo=1, hi=2000):
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
                out.append((i, L, s))
                i += 4 + L
                i = (i + 3) & ~3
                continue
        i += 1
    return out


def iter_objects(path):
    uf = UnityFile(path, verbose=False)
    for o in uf.objects:
        raw = uf.buf[o["abs"]:o["abs"] + o["byteSize"]]
        if not raw:
            continue
        yield o, raw


def main():
    sys.stdout.reconfigure(errors="backslashreplace")
    stats = collections.Counter()
    rows = []
    files = [f for f in sorted(os.listdir(DATA))
             if f.endswith(".assets") or (f.startswith("level") and "." not in f)]
    for fname in files:
        p = os.path.join(DATA, fname)
        if not os.path.exists(p):
            continue
        try:
            objs = list(iter_objects(p))
        except Exception as e:
            print("  [skip] %s : %r" % (fname, e))
            continue
        for o, raw in objs:
            if o["classID"] not in (49, 114):     # TextAsset, MonoBehaviour
                continue
            try:
                strs = unity_strings(raw)
            except Exception:
                continue
            for (off, L, s) in strs:
                for name, rx in PATTERNS:
                    if rx.search(s):
                        stats[name] += 1
                        rows.append((fname, o["classID"], o["pathID"], o["abs"] + off, name, s))
    # DLL strings
    dll = os.path.join(DATA, "Managed", "Assembly-CSharp.dll")
    if os.path.exists(dll):
        pe = PE(dll)
        for s in parse_us(pe):
            for name, rx in PATTERNS:
                if rx.search(s):
                    stats[name] += 1
                    rows.append(("Assembly-CSharp.dll", 0, 0, 0, name, s))

    print("=== 命中统计 ===")
    for name, _ in PATTERNS:
        print("  %-22s %d" % (name, stats[name]))
    print("=== 明细（每个模式前 30 条）===")
    shown = collections.Counter()
    for (fname, cls, pid, off, name, s) in rows:
        if shown[name] >= 30:
            continue
        shown[name] += 1
        body = s.replace("\n", "\\n")
        if len(body) > 150:
            body = body[:150] + "…"
        print("  [%s] %s cls=%s pathID=0x%x @%d\n     %s" % (name, fname, cls, pid, off, body.encode("ascii", "backslashreplace").decode()))

    out = os.path.join(ROOT, "_hanhua", "out", "escape_artifacts.txt")
    with open(out, "w", encoding="utf-8") as fh:
        for (fname, cls, pid, off, name, s) in rows:
            fh.write("%s\t%s\t%d\t%s\t%s\n" % (fname, cls, pid, off, name, s.replace("\n", "\\n")))
    print("清单 -> " + out)


if __name__ == "__main__":
    main()
