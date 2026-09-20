#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Proper minimal CFF (Type2 CharString) INDEX reader for OTTO fonts.
Prints the CharStrings INDEX count and the byte length of selected glyph
programs, so we can tell an EMPTY glyph slot (only `endchar`) from a real
outline.  That distinguishes "font maps a code point to an empty slot" from
"Unity bug".

Usage: python cff_outlines.py <font.otf> [gid,gid,...]
"""
import struct
import sys

sys.path.insert(0, "F:/Steam/steamapps/common/琴葉姉妹とライサント島の伝説/kotonoha/_hanhua/tools")
from otf_cmap import Sfnt


def read_index(d, p):
    """Return (items, next_pos) where items are (start, end) byte ranges."""
    count = struct.unpack(">H", d[p:p + 2])[0]
    p += 2
    if count == 0:
        return [], p
    off_size = d[p]
    p += 1
    offs = []
    for i in range(count + 1):
        q = p + i * off_size
        if off_size == 1:
            offs.append(d[q])
        elif off_size == 2:
            offs.append(struct.unpack(">H", d[q:q + 2])[0])
        elif off_size == 3:
            offs.append(int.from_bytes(d[q:q + 3], "big"))
        else:
            offs.append(int.from_bytes(d[q:q + 4], "big"))
    data_start = p + (count + 1) * off_size - 1
    items = [(data_start + offs[i], data_start + offs[i + 1]) for i in range(count)]
    return items, data_start + offs[-1]


def parse_topdict(td):
    """Return {operator: [operands]} for a CFF Top/Private DICT."""
    ops = {}
    operands = []
    i = 0
    while i < len(td):
        b = td[i]
        if b <= 21:
            if b == 12:
                op = 1200 + td[i + 1]
                i += 2
            else:
                op = b
                i += 1
            ops[op] = operands
            operands = []
        elif b == 28:
            operands.append(struct.unpack(">h", td[i + 1:i + 3])[0])
            i += 3
        elif b == 29:
            operands.append(struct.unpack(">i", td[i + 1:i + 5])[0])
            i += 5
        elif b == 30:
            j = i + 1
            buf = ""
            done = False
            while j < len(td) and not done:
                v = td[j]
                j += 1
                for nib in (v >> 4, v & 0xF):
                    if nib == 0xF:
                        done = True
                        break
                    buf += "0123456789.EE?-?"[nib] if nib < 14 else ""
            operands.append(buf)
            i = j
        elif 32 <= b <= 246:
            operands.append(b - 139)
            i += 1
        elif 247 <= b <= 250:
            operands.append((b - 247) * 256 + td[i + 1] + 108)
            i += 2
        elif 251 <= b <= 254:
            operands.append(-(b - 251) * 256 - td[i + 1] - 108)
            i += 2
        else:
            i += 1
    return ops


def main():
    path = sys.argv[1]
    wanted = []
    if len(sys.argv) > 2:
        wanted = [int(x) for x in sys.argv[2].split(",")]
    f = Sfnt(path)
    d = f.data
    off, tlen = f.tables["CFF "]
    p = off
    major, minor, hdr_size, off_size = d[p], d[p + 1], d[p + 2], d[p + 3]
    print("CFF version %d.%d hdrSize=%d offSize=%d" % (major, minor, hdr_size, off_size))
    p += hdr_size
    names, p = read_index(d, p)
    topdicts, p = read_index(d, p)
    strings, p = read_index(d, p)
    print("Name INDEX=%d TopDICT=%d String INDEX=%d" % (len(names), len(topdicts), len(strings)))
    if names:
        print("  font name: %s" % d[names[0][0]:names[0][1]].decode("latin-1"))
    td = d[topdicts[0][0]:topdicts[0][1]]
    ops = parse_topdict(td)
    print("  TopDICT ops: %s" % sorted(ops.keys()))
    print("  CharStrings off=%s  Private=%s" % (ops.get(17), ops.get(18)))
    print("  ROS(1200)=%s  CIDCount(1234)=%s" % (ops.get(1200), ops.get(1234)))
    if 17 not in ops:
        print("no CharStrings")
        return
    cs_items, _ = read_index(d, off + ops[17][0])
    print("CharStrings INDEX count = %d" % len(cs_items))

    if wanted:
        print("\ngid    charstring bytes   first bytes")
        for gid in wanted:
            if gid < len(cs_items):
                s, e = cs_items[gid]
                body = d[s:e]
                print("%-6d %-18d %s" % (gid, len(body), body[:24].hex()))
            else:
                print("%-6d OUT OF RANGE (>%d)" % (gid, len(cs_items) - 1))

    # statistics: how many charstrings are "empty" (endchar only, <= 3 bytes)
    empty = 0
    sizes = []
    for s, e in cs_items:
        n = e - s
        sizes.append(n)
        if n <= 4:
            empty += 1
    print("\ncharstrings: count=%d empty(<=4 bytes)=%d min=%d max=%d"
          % (len(cs_items), empty, min(sizes), max(sizes)))
    return


if __name__ == "__main__":
    main()
