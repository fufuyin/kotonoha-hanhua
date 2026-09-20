#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test WHY Unity's FontEngine refused 74 code points that the OTF's cmap does map.

Hypothesis H1: the glyph slot exists in cmap but there is no outline for it
(Source Han Sans language-specific OTFs map code points to glyph ids that are
absent/empty in the CFF CharStrings) -> FT_Load_Glyph fails -> TMP reports missing.

This script compares, for every refused code point:
  * the glyph id from each cmap subtable
  * maxp.numGlyphs
  * the CFF CharStrings INDEX count (the actual number of outline glyphs)
and reports how many refused ids fall outside the outline range.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from otf_cmap import Sfnt

OTF = r"F:\Application\Unity\fonts\NotoSansCJKsc-Regular.otf"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out")


def cff_charstrings_count(data, tables):
    off, _ = tables["CFF "]
    p = off
    major, minor, hdrSize = data[p], data[p + 1], data[p + 2]
    p += hdrSize
    # Name INDEX
    count = struct.unpack(">H", data[p:p + 2])[0]
    p += 2
    if count:
        offSize = data[p]
        p += 1
        ends = p + count * offSize
        dataEnd = ends + (struct.unpack(">B", data[ends - 1:ends])[0] if offSize == 1 else 0)
        # generic: read last offset
        if offSize == 1:
            last = data[ends - 1]
        elif offSize == 2:
            last = struct.unpack(">H", data[ends - 2:ends])[0]
        elif offSize == 3:
            last = int.from_bytes(data[ends - 3:ends], "big")
        else:
            last = int.from_bytes(data[ends - 4:ends], "big")
        p = ends + last - 1
    else:
        p += 1
    idx_end = p  # end of Name INDEX
    # Top DICT INDEX
    count = struct.unpack(">H", data[p:p + 2])[0]
    p += 2
    offSize = data[p]
    p += 1
    offs = []
    for i in range(count + 1):
        if offSize == 1:
            offs.append(data[p + i])
        elif offSize == 2:
            offs.append(struct.unpack(">H", data[p + 2 * i:p + 2 * i + 2])[0])
        elif offSize == 3:
            offs.append(int.from_bytes(data[p + 3 * i:p + 3 * i + 3], "big"))
        else:
            offs.append(int.from_bytes(data[p + 4 * i:p + 4 * i + 4], "big"))
    base = p + (count + 1) * offSize - 1
    topdict = data[base + offs[0]:base + offs[1]]
    # parse TopDICT for CharStrings (op 17)
    charstrings = None
    operands = []
    i = 0
    while i < len(topdict):
        b = topdict[i]
        if b <= 21:
            op = b
            if b == 12:
                op = 1200 + topdict[i + 1]
                i += 1
            if op == 17 and operands:
                charstrings = operands[-1]
            operands = []
            i += 1
        elif b == 28:
            operands.append(struct.unpack(">h", topdict[i + 1:i + 3])[0])
            i += 3
        elif b == 29:
            operands.append(struct.unpack(">i", topdict[i + 1:i + 5])[0])
            i += 5
        elif b == 30:
            j = i + 1
            while j < len(topdict):
                v = topdict[j]
                j += 1
                if (v & 0xF) == 0xF or (v >> 4) == 0xF:
                    break
            operands.append(0)
            i = j
        elif 32 <= b <= 246:
            operands.append(b - 139)
            i += 1
        elif 247 <= b <= 250:
            operands.append((b - 247) * 256 + topdict[i + 1] + 108)
            i += 2
        elif 251 <= b <= 254:
            operands.append(-(b - 251) * 256 - topdict[i + 1] - 108)
            i += 2
        else:
            i += 1
    if charstrings is None:
        return None, None
    q = off + charstrings
    n = struct.unpack(">H", data[q:q + 2])[0]
    return n, charstrings


def main():
    sys.stdout.reconfigure(errors="backslashreplace")
    f = Sfnt(OTF)
    d = f.data
    numGlyphs = None
    if "maxp" in f.tables:
        mo, _ = f.tables["maxp"]
        numGlyphs = struct.unpack(">H", d[mo + 4:mo + 6])[0]
    print("maxp.numGlyphs = %s" % numGlyphs)
    try:
        cs, csoff = cff_charstrings_count(d, f.tables)
        print("CFF CharStrings count = %s (offset %s)" % (cs, csoff))
    except Exception as e:
        cs = None
        print("CFF parse failed: %r" % (e,))
    print("tables: %s" % ",".join(sorted(f.tables)))

    missing = open(os.path.join(OUT, "baked_missing_present_in_font.txt"), encoding="utf-8").read()
    cps = [ord(c) for c in missing]

    subs = f.all_cmaps()
    fmt4 = None
    fmt12 = None
    for pid, eid, fmt, m in subs:
        if fmt == 4 and fmt4 is None:
            fmt4 = m
        if fmt == 12 and fmt12 is None:
            fmt12 = m

    print("\ncp      fmt4   fmt12   inOutline(count=%s)" % cs)
    bad = 0
    outside = 0
    for cp in cps:
        g4 = fmt4.get(cp, 0) if fmt4 else 0
        g12 = fmt12.get(cp, 0) if fmt12 else 0
        inout = ""
        if cs is not None:
            if g12 and g12 <= cs:
                inout = "yes"
            else:
                inout = "NO"
                outside += 1
        if g4 != g12:
            bad += 1
        print("U+%04X  %-6d %-7d %s" % (cp, g4, g12, inout))
    print("\nrefused=%d  fmt4!=fmt12=%d  glyph_id_beyond_CFF_outlines=%d" % (len(cps), bad, outside))

    # how many of the 7803 baked chars sit beyond the outline range?
    baked = set()
    print("\nsanity: max glyph id present in cmap = %d" % (max(fmt12.values()) if fmt12 else -1))


if __name__ == "__main__":
    main()
