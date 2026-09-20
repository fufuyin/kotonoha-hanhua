#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按 pathID（或 pathID 区间）导出 Unity 对象里的字符串，用于判断某条 UI 文本的上下文。

用法:
  python dump_object_strings.py <assets 文件> 0x86b7
  python dump_object_strings.py <assets 文件> --range 0x86a0 0x86d0
"""
import argparse
import struct
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from unityfile import UnityFile


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
    ap.add_argument("path")
    ap.add_argument("pathid", nargs="?")
    ap.add_argument("--range", nargs=2)
    a = ap.parse_args()
    sys.stdout.reconfigure(errors="backslashreplace")
    uf = UnityFile(a.path, verbose=False)
    if a.range:
        lo, hi = int(a.range[0], 16), int(a.range[1], 16)
        objs = [o for o in uf.objects if lo <= o["pathID"] <= hi]
    else:
        pid = int(a.pathid, 16)
        objs = [o for o in uf.objects if o["pathID"] == pid]
    print("matched objects: %d" % len(objs))
    for o in objs:
        raw = uf.buf[o["abs"]:o["abs"] + o["byteSize"]]
        try:
            strs = unity_strings(raw)
        except Exception:
            strs = []
        interesting = [t for t in strs if t[2].strip()]
        print("  pathID=0x%x cls=%s size=%d strings=%d" % (o["pathID"], o["classID"], o["byteSize"], len(interesting)))
        for off, L, s in interesting[:14]:
            body = s.replace("\n", "\\n")
            if len(body) > 120:
                body = body[:120] + "…"
            print("      @%-8d L=%-5d %s" % (off, L, body.encode("ascii", "backslashreplace").decode()))


if __name__ == "__main__":
    main()
