#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check the Unity-editor YAML TMP font asset produced by FontCreator (KotonohaCreator.asset)."""
import io
import os
import re
import sys

ASSET = r"F:\Application\Unity\Assets\BakedFonts\KotonohaCreator.asset"


def main():
    sys.stdout.reconfigure(errors="backslashreplace")
    data = open(ASSET, "rb").read()
    print("asset bytes = %d" % len(data))

    for m in re.finditer(rb"^Texture2D:\s*$", data, re.M):
        seg = data[m.start():m.start() + 4000]
        w = re.search(rb"m_Width:\s*(\d+)", seg)
        h = re.search(rb"m_Height:\s*(\d+)", seg)
        f = re.search(rb"m_TextureFormat:\s*(\d+)", seg)
        nm = re.search(rb"m_Name:\s*(.*)", seg)
        print("Texture2D name=%s %sx%s fmt=%s"
              % (nm.group(1).decode("utf-8", "replace") if nm else "?",
                 w.group(1).decode() if w else "?", h.group(1).decode() if h else "?",
                 f.group(1).decode() if f else "?"))

    for m in re.finditer(rb"^Material:\s*$", data, re.M):
        seg = data[m.start():m.start() + 3000]
        nm = re.search(rb"m_Name:\s*(.*)", seg)
        sh = re.search(rb"m_Shader:\s*\{fileID:\s*(-?\d+)", seg)
        print("Material name=%s shaderFileID=%s"
              % (nm.group(1).decode("utf-8", "replace") if nm else "?",
                 sh.group(1).decode() if sh else "?"))

    # font asset (MonoBehaviour) block
    for m in re.finditer(rb"^MonoBehaviour:\s*$", data, re.M):
        seg = data[m.start():m.start() + 6000]
        ver = re.search(rb"m_Version:\s*(.*)", seg)
        aw = re.search(rb"m_AtlasWidth:\s*(\d+)", seg)
        ah = re.search(rb"m_AtlasHeight:\s*(\d+)", seg)
        ap = re.search(rb"m_AtlasPadding:\s*(\d+)", seg)
        arm = re.search(rb"m_AtlasRenderMode:\s*(\d+)", seg)
        apm = re.search(rb"m_AtlasPopulationMode:\s*(\d+)", seg)
        mat = re.search(rb"m_Material:\s*\{fileID:\s*(-?\d+)", seg)
        fw = re.search(rb"m_FontWeightTable:", seg)
        ff = re.search(rb"m_FontFeatureTable:", seg)
        print("MonoBehaviour version=%s atlas=%sx%s padding=%s renderMode=%s popMode=%s m_Material=%s weightTable=%s featureTable=%s"
              % (ver.group(1).decode("utf-8", "replace") if ver else "?",
                 aw.group(1).decode() if aw else "?", ah.group(1).decode() if ah else "?",
                 ap.group(1).decode() if ap else "?", arm.group(1).decode() if arm else "?",
                 apm.group(1).decode() if apm else "?",
                 mat.group(1).decode() if mat else "?",
                 "yes" if fw else "no", "yes" if ff else "no"))

    uni = re.findall(rb"^\s*m_Unicode:\s*(\d+)\s*$", data, re.M)
    gid = re.findall(rb"^\s*m_GlyphIndex:\s*(\d+)\s*$", data, re.M)
    print("m_Unicode entries=%d  m_GlyphIndex entries=%d" % (len(uni), len(gid)))
    ret = re.findall(rb"^\s*m_Rect:\s*\{x:\s*(-?\d+),\s*y:\s*(-?\d+),\s*width:\s*(\d+),\s*height:\s*(\d+)\}", data, re.M)
    if ret:
        nz = sum(1 for r in ret if int(r[2]) > 0 and int(r[3]) > 0)
        print("glyph rects=%d nonEmpty=%d" % (len(ret), nz))
        mx = max(int(r[0]) + int(r[2]) for r in ret)
        my = max(int(r[1]) + int(r[3]) for r in ret)
        print("max rect extent = %d x %d (must be <= atlas size)" % (mx, my))


if __name__ == "__main__":
    main()
