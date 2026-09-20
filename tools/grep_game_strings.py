#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在游戏文本里做子串检索（TextAsset / MonoBehaviour / Assembly-CSharp.dll #US）。
复用性工具：查某句话/某个字符在哪些对象里出现，用于判断 UI 语义与改写范围。

用法:
  python grep_game_strings.py 手に入れた
  python grep_game_strings.py "<i>" --limit 20
  python grep_game_strings.py 獲得 --files resources.assets sharedassets0.assets
"""
import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
from netmeta import PE, parse_us

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DATA = os.path.join(ROOT, "kotonoha_Data")


def unity_strings(raw, lo=1, hi=4000):
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
    ap = argparse.ArgumentParser()
    ap.add_argument("pattern")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--files", nargs="*")
    ap.add_argument("--regex", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(errors="backslashreplace")

    if a.regex:
        rx = re.compile(a.pattern)
    else:
        rx = None

    def hit(s):
        return bool(rx.search(s)) if rx else (a.pattern in s)

    files = a.files or [f for f in sorted(os.listdir(DATA))
                        if f.endswith(".assets") or (f.startswith("level") and "." not in f)]
    shown = 0
    total = 0
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
            raw = uf.buf[o["abs"]:o["abs"] + o["byteSize"]]
            if not raw:
                continue
            try:
                strs = unity_strings(raw)
            except Exception:
                continue
            for off, L, s in strs:
                if hit(s):
                    total += 1
                    if shown < a.limit:
                        shown += 1
                        body = s.replace("\n", "\\n")
                        if len(body) > 200:
                            body = body[:200] + "…"
                        print("  %s %s pathID=0x%x @%d L=%d\n     %s"
                              % (fname, o["classID"], o["pathID"], o["abs"] + off, L,
                                 body.encode("ascii", "backslashreplace").decode()))
    dll = os.path.join(DATA, "Managed", "Assembly-CSharp.dll")
    if os.path.exists(dll):
        for s in parse_us(PE(dll)):
            if hit(s):
                total += 1
                if shown < a.limit:
                    shown += 1
                    body = s.replace("\n", "\\n")
                    if len(body) > 200:
                        body = body[:200] + "…"
                    print("  Assembly-CSharp.dll #US\n     " + body.encode("ascii", "backslashreplace").decode())
    print("命中 %d 条（显示 %d 条）" % (total, shown))


if __name__ == "__main__":
    main()
