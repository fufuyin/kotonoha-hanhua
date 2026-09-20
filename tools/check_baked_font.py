#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verify a Unity-text (YAML) TMP font asset produced by FontBaker.Bake:
  * report the atlas Texture2D (width/height/format/typless-data bytes)
  * extract every m_Unicode in the font asset's m_CharacterTable
  * diff against the bake charset and print the MISSING code points
No third-party deps.
"""
import io
import os
import re
import sys

ASSET = r"F:\Application\Unity\Assets\BakedFonts\KotonohaFont_00.asset"
CHARSET = r"F:\Application\Unity\charset.txt"

RE_UNICODE = re.compile(rb"^\s*m_Unicode:\s*(\d+)\s*$", re.M)
RE_GLYPHIDX = re.compile(rb"^\s*m_GlyphIndex:\s*(\d+)\s*$", re.M)


def load_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def grab(texture_bytes, key):
    m = re.search(key + rb":\s*(-?\d+)", texture_bytes)
    return int(m.group(1)) if m else None


def safe(s):
    """Console-safe text for the GBK Windows console."""
    return s.encode("ascii", "backslashreplace").decode("ascii")


def main():
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except Exception:
        pass
    data = load_bytes(ASSET)
    print("asset bytes = %d" % len(data))

    # --- atlas texture(s) ---
    tex_headers = list(re.finditer(rb"^Texture2D:\s*$", data, re.M))
    print("Texture2D sections = %d" % len(tex_headers))
    for i, m in enumerate(tex_headers):
        start = m.start()
        end = data.find(b"^---", start + 1, re.M)
        if end < 0:
            end = len(data)
        seg = data[start:end]
        w = grab(seg, rb"m_Width")
        h = grab(seg, rb"m_Height")
        fmt = grab(seg, rb"m_TextureFormat")
        td = re.search(rb"_typelessdata:\s*([0-9a-fA-F]*)", seg)
        tlen = len(td.group(1)) // 2 if td else 0
        print("  tex[%d] %dx%d fmt=%s typelessdata=%d bytes (implied %d B/px)"
              % (i, w or 0, h or 0, fmt, tlen, (tlen // (w * h)) if w and h and tlen else 0))

    # --- character table ---
    uni = [int(x) for x in RE_UNICODE.findall(data)]
    uni_set = set(uni)
    print("m_CharacterTable entries = %d (distinct %d)" % (len(uni), len(uni_set)))

    # --- glyph table (count of Glyph blocks referenced by m_GlyphTable) ---
    n_glyphid = len(RE_GLYPHIDX.findall(data))
    print("m_GlyphIndex occurrences = %d" % n_glyphid)

    # --- charset diff ---
    with io.open(CHARSET, "r", encoding="utf-8") as f:
        charset = f.read()
    want = [ord(c) for c in charset]
    want_set = set(want)
    print("charset.txt len=%d distinct=%d" % (len(want), len(want_set)))

    missing = sorted(want_set - uni_set)
    print("MISSING from baked font: %d" % len(missing))
    if missing:
        s = "".join(chr(c) for c in missing)
        print("missing chars (escaped): " + safe(s))
        # bucket ranges
        buckets = {}
        for c in missing:
            buckets.setdefault(c >> 8, 0)
            buckets[c >> 8] += 1
        print("missing by high-byte plane:")
        for k in sorted(buckets):
            print("  U+%02Xxx : %d" % (k, buckets[k]))

    extra = sorted(uni_set - want_set)
    print("EXTRA in baked font (not in charset): %d" % len(extra))
    if extra[:50]:
        print("extra sample: " + safe("".join(chr(c) for c in extra[:120])))

    # write the missing list for later use
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", "baked_missing.txt")
    out = os.path.abspath(out)
    with io.open(out, "w", encoding="utf-8") as f:
        f.write("".join(chr(c) for c in missing))
    print("wrote %s" % out)


if __name__ == "__main__":
    main()
