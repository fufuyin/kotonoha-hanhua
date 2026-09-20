#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清掉「设计期假名样张」占位文本（菜单等界面里真会被玩家看到的乱码来源）。

判定规则（保守，避免误伤真实日文词）：
  去掉 <i></i> 等标签、换行、全角空格后，剩余字符必须**全部**属于经典样张字集
  {あ い う え お か き く け こ さ し す せ そ た ち つ て と な に ぬ ね の}
  且必须含有典型样张连续片段（あいう / あああ / かきく / さしす / たちつ / なにぬ），
  这样 あいさつ、あなた 这类真实词不会被匹配。

替换方式：把每个样张假名字符**原地替换为全角空格 U+3000**（3 字节 → 3 字节），
  因此长度、标签、对象布局**完全不变**，无需补齐。

用法:
  python blank_placeholder_samples.py [--apply]
"""
import argparse
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DATA = os.path.join(ROOT, "kotonoha_Data")

SAMPLE = set("あいうえおかきくけこさしすせそたちつてとなにぬねの")
NGRAMS = ("あいう", "あああ", "かきく", "さしす", "たちつ", "なにぬ")
TAGS = ("<i>", "</i>", "<b>", "</b>")


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


def is_sample(s):
    t = s
    for tag in TAGS:
        t = t.replace(tag, "")
    t = t.replace("\n", "").replace("\r", "").replace("\u3000", "")
    if not t:
        return False
    if not all(c in SAMPLE for c in t):
        return False
    return any(ng in t for ng in NGRAMS)


def blank(s):
    return "".join("\u3000" if c in SAMPLE else c for c in s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(errors="backslashreplace")

    files = [f for f in sorted(os.listdir(DATA))
             if f.endswith(".assets") or (f.startswith("level") and "." not in f)]
    grand_total = 0
    for fname in files:
        p = os.path.join(DATA, fname)
        if not os.path.exists(p):
            continue
        try:
            uf = UnityFile(p, verbose=False)
        except Exception:
            continue
        plans = []
        for o in uf.objects:
            if o["classID"] not in (49, 114):
                continue
            if o["classID"] == 114 and o["byteSize"] > 100000:
                continue
            raw = uf.buf[o["abs"]:o["abs"] + o["byteSize"]]
            for off, L, s in unity_strings(raw):
                if not is_sample(s):
                    continue
                nb = blank(s).encode("utf-8")
                assert len(nb) == len(s.encode("utf-8")), "length changed!"
                plans.append((o["abs"] + off, L, s, nb))
        if not plans:
            continue
        grand_total += len(plans)
        print("%-22s %d 条" % (fname, len(plans)))
        for abs_off, L, s, nb in plans[:3]:
            print("    @%d L=%d  %r" % (abs_off, L, s.encode("ascii", "backslashreplace").decode()))
        if a.apply:
            backup = p + ".before_samples"
            if not os.path.exists(backup):
                shutil.copyfile(p, backup)
            size_before = os.path.getsize(p)
            obj_before = len(uf.objects)
            buf = bytearray(open(p, "rb").read())
            for abs_off, L, s, nb in plans:
                buf[abs_off:abs_off + L] = nb
            open(p, "wb").write(bytes(buf))
            uf2 = UnityFile(p, verbose=False)
            size_after = os.path.getsize(p)
            left = 0
            for o in uf2.objects:
                if o["classID"] not in (49, 114):
                    continue
                raw = uf2.buf[o["abs"]:o["abs"] + o["byteSize"]]
                left += sum(1 for _, _, s in unity_strings(raw) if is_sample(s))
            print("    [verify] obj %d->%d  size %d->%d  remainingSamples=%d  backup=%s"
                  % (obj_before, len(uf2.objects), size_before, size_after, left, os.path.basename(backup)))
    print("\n总计待清理样张串: %d 条" % grand_total)
    if not a.apply:
        print("[dry-run] 未写盘；确认后加 --apply")


if __name__ == "__main__":
    main()
