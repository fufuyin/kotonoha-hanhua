#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimal pure-stdlib sfnt (TTF/OTF) cmap reader.
Purpose: decide whether a code point is really *in* the font file, so we can tell
"the font lacks it" apart from "Unity FontEngine failed to give me a glyph index".

Usage:
  python otf_cmap.py <font.otf|ttf> [--check 0x2026,0x2014,...]
                      [--coverage] [--range 0x20,0x7E]
"""
import struct
import sys


class Sfnt(object):
    def __init__(self, path):
        with open(path, "rb") as f:
            self.data = f.read()
        d = self.data
        tag = d[:4]
        self.flavor = tag.decode("latin-1")
        numTables = struct.unpack(">H", d[4:6])[0]
        self.tables = {}
        for i in range(numTables):
            off = 12 + 16 * i
            name = d[off:off + 4].decode("latin-1")
            toff, tlen = struct.unpack(">II", d[off + 8:off + 16])
            self.tables[name] = (toff, tlen)
        self.cmap = self._read_cmap()

    def _read_cmap(self):
        off, _ = self.tables["cmap"]
        d = self.data
        n = struct.unpack(">H", d[off + 2:off + 4])[0]
        subtables = []
        for i in range(n):
            p = off + 4 + 8 * i
            pid, eid, so = struct.unpack(">HHI", d[p:p + 8])
            fmt = struct.unpack(">H", d[off + so:off + so + 2])[0]
            subtables.append((pid, eid, fmt, off + so))
        # prefer (3,10) fmt12, then (3,1) fmt4, then (0,x)
        order = {(3, 10): 0, (3, 1): 1, (0, 4): 2, (0, 3): 3, (0, 6): 4,
                 (0, 0): 5, (3, 0): 6}
        best = None
        for st in subtables:
            k = (st[0], st[1])
            if k in order:
                rank = order[k]
                if best is None or rank < best[0]:
                    best = (rank, st)
        if best is None:
            return {}
        _, (pid, eid, fmt, so) = best
        self.chosen = (pid, eid, fmt)
        if fmt == 4:
            return self._fmt4(so)
        if fmt == 12:
            return self._fmt12(so)
        if fmt == 6:
            return self._fmt6(so)
        if fmt == 0:
            return self._fmt0(so)
        return {}

    def _fmt4(self, so):
        d = self.data
        segX2 = struct.unpack(">H", d[so + 6:so + 8])[0]
        seg = segX2 // 2
        endO = so + 14
        ends = struct.unpack(">%dH" % seg, d[endO:endO + segX2])
        startO = endO + segX2 + 2
        starts = struct.unpack(">%dH" % seg, d[startO:startO + segX2])
        deltaO = startO + segX2
        deltas = struct.unpack(">%dh" % seg, d[deltaO:deltaO + segX2])
        rangeO = deltaO + segX2
        ranges = struct.unpack(">%dH" % seg, d[rangeO:rangeO + segX2])
        m = {}
        for i in range(seg):
            for c in range(starts[i], min(ends[i], 0xFFFF) + 1):
                if c == 0xFFFF:
                    continue
                gi = (c + deltas[i]) & 0xFFFF
                if ranges[i] != 0:
                    gp = rangeO + 2 * i + ranges[i] + 2 * (c - starts[i])
                    if gp + 2 > len(d):
                        continue
                    gi = struct.unpack(">H", d[gp:gp + 2])[0]
                    if gi:
                        gi = (gi + deltas[i]) & 0xFFFF
                if gi:
                    m[c] = gi
        return m

    def _fmt6(self, so):
        d = self.data
        first, cnt = struct.unpack(">HH", d[so + 6:so + 10])
        m = {}
        for i in range(cnt):
            gi = struct.unpack(">H", d[so + 10 + 2 * i:so + 12 + 2 * i])[0]
            if gi:
                m[first + i] = gi
        return m

    def _fmt0(self, so):
        d = self.data
        m = {}
        for c in range(256):
            gi = d[so + 6 + c]
            if gi:
                m[c] = gi
        return m

    def _fmt12(self, so):
        d = self.data
        n = struct.unpack(">I", d[so + 12:so + 16])[0]
        m = {}
        for i in range(n):
            p = so + 16 + 12 * i
            s, e, g = struct.unpack(">III", d[p:p + 12])
            for c in range(s, e + 1):
                m[c] = g + (c - s)
        return m

    def subtable_headers(self):
        """[(platformID, encodingID, format, absoluteOffset), ...]"""
        off, _ = self.tables["cmap"]
        d = self.data
        n = struct.unpack(">H", d[off + 2:off + 4])[0]
        out = []
        for i in range(n):
            p = off + 4 + 8 * i
            pid, eid, so = struct.unpack(">HHI", d[p:p + 8])
            fmt = struct.unpack(">H", d[off + so:off + so + 2])[0]
            out.append((pid, eid, fmt, off + so))
        return out

    def map_subtable(self, so, fmt):
        if fmt == 4:
            return self._fmt4(so)
        if fmt == 12:
            return self._fmt12(so)
        if fmt == 6:
            return self._fmt6(so)
        if fmt == 0:
            return self._fmt0(so)
        return {}

    def all_cmaps(self):
        """[(pid, eid, fmt, {cp: gid}), ...]"""
        out = []
        for pid, eid, fmt, so in self.subtable_headers():
            try:
                m = self.map_subtable(so, fmt)
            except Exception:
                m = {}
            out.append((pid, eid, fmt, m))
        return out

    def has(self, cp):
        return cp in self.cmap

    def glyph(self, cp):
        return self.cmap.get(cp, 0)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    path = args[0]
    f = Sfnt(path)
    print("font=%s flavor=%s tables=%s cmap_subtable=%s mapped=%d"
          % (path, f.flavor, ",".join(sorted(f.tables)), getattr(f, "chosen", None), len(f.cmap)))
    check = None
    coverage = False
    rng = None
    i = 1
    while i < len(args):
        if args[i] == "--check":
            check = [int(x, 0) for x in args[i + 1].split(",")]
            i += 2
        elif args[i] == "--coverage":
            coverage = True
            i += 1
        elif args[i] == "--range":
            a, b = args[i + 1].split(",")
            rng = (int(a, 0), int(b, 0))
            i += 2
        else:
            i += 1
    if check:
        for cp in check:
            print("  U+%04X %s glyphIndex=%d" % (cp, "HAS" if f.has(cp) else "MISSING", f.glyph(cp)))
    if coverage:
        planes = {}
        for cp in f.cmap:
            planes.setdefault(cp >> 8, 0)
            planes[cp >> 8] += 1
        print("coverage by plane (high byte):")
        for k in sorted(planes):
            print("  U+%02Xxx : %d" % (k, planes[k]))
    if rng:
        miss = [c for c in range(rng[0], rng[1] + 1) if not f.has(c)]
        print("range U+%04X-U+%04X missing %d: %s"
              % (rng[0], rng[1], len(miss), "".join(chr(c) for c in miss[:200])))


if __name__ == "__main__":
    main()
