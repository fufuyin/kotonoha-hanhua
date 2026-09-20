#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查「不可读语言」符号是否被新字体覆盖：
  - 对比当前 Assembly-CSharp.dll 与原版 .bak 的 #US 字符串差异（找出当初被替换的 randomWord 符号）
  - 逐字符查 creator_report.tsv 的渲染状态
结论决定：最终补丁是否要恢复 .bak。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from netmeta import PE, parse_us

GAME = r"F:\Steam\steamapps\common\琴葉姉妹とライサント島の伝説\kotonoha\kotonoha_Data\Managed"
CUR = os.path.join(GAME, "Assembly-CSharp.dll")
BAK = os.path.join(GAME, "Assembly-CSharp.dll.bak")
REPORT = r"F:\Application\Unity\creator_report.tsv"


def strings(path):
    pe = PE(path)
    return parse_us(pe)


def status_map():
    st = {}
    for line in open(REPORT, encoding="utf-8"):
        f = line.rstrip("\n").split("\t")
        if len(f) >= 12 and f[0].startswith("U+"):
            st[int(f[0][2:], 16)] = f[11]
    return st


def main():
    sys.stdout.reconfigure(errors="backslashreplace")
    cur = strings(CUR)
    print("current dll #US strings = %d" % len(cur))
    if os.path.exists(BAK):
        bak = strings(BAK)
        print("backup  dll #US strings = %d" % len(bak))
        only_cur = [s for s in cur if s not in bak]
        only_bak = [s for s in bak if s not in cur]
        print("\n只在当前 DLL 里的字符串 (%d):" % len(only_cur))
        for s in only_cur[:40]:
            print("   " + s.encode("ascii", "backslashreplace").decode())
        print("\n只在备份 DLL 里的字符串 (%d):" % len(only_bak))
        for s in only_bak[:40]:
            print("   " + s.encode("ascii", "backslashreplace").decode())
    else:
        print("no .bak")

    st = status_map()
    # symbols currently shipped by the patched dll (the ones the 5-font intersection provided)
    current_symbols = "。、々「」『【〔《〈〉"
    print("\n当前 DLL 的 randomWord 符号覆盖情况:")
    bad = []
    for c in current_symbols:
        s = st.get(ord(c), "NOT-IN-REPORT")
        if s != "ok":
            bad.append(c)
        print("   %s U+%04X -> %s" % (c.encode("ascii", "backslashreplace").decode(), ord(c), s))
    print("   未覆盖: %s" % ("".join(bad) if bad else "无"))

    if os.path.exists(BAK):
        # characters that appear only in the backup's strings
        bak = strings(BAK)
        only_bak_chars = set()
        curset = set(cur)
        for s in bak:
            if s not in curset:
                only_bak_chars |= {ord(c) for c in s}
        only_bak_chars = {c for c in only_bak_chars if c >= 0x20}
        uncovered = sorted(c for c in only_bak_chars if st.get(c, "NOT-IN-REPORT") != "ok")
        print("\n只在备份 DLL 出现、且新字体未覆盖的码位 = %d" % len(uncovered))
        if uncovered:
            print("   " + "".join(chr(c) for c in uncovered[:200]).encode("ascii", "backslashreplace").decode())


if __name__ == "__main__":
    main()
