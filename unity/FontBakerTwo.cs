// FontBakerTwo -- two-source TMP font bake, replicating TMP's Font Asset Creator path.
//
// Why: no off-the-shelf rounded CJK font covers this game's punctuation (・ U+30FB and the
// ideographic space U+3000 are missing from 幼圆 / 寒蝉圆黑体), so the round look and full
// coverage must come from TWO fonts merged into ONE atlas:
//     primary  = fontsource.txt          (the look: e.g. ChillRoundGothic_Regular.otf)
//     filler   = fontsource_filler.txt   (only for code points the primary lacks)
// Padding is 10 (matching the game's original materials, whose _GradientScale is 11) so that
// outlines/softness render at the same scale as before; our previous bake used padding 4.
//
// Two render passes go into two buffers; pass-2 pixels are copied into the main buffer using
// the packed rects (no reliance on Unity's overwrite semantics).
//
//   Unity.exe -batchmode -nographics -quit -projectPath F:\Application\Unity \
//             -executeMethod FontBakerTwo.Bake -logFile F:\Application\Unity\twobake.log
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using TMPro;
using UnityEditor;
using UnityEngine;
using UnityEngine.TextCore;
using UnityEngine.TextCore.LowLevel;

public static class FontBakerTwo
{
    const string PrimaryCfg = @"F:\Application\Unity\fontsource.txt";
    const string FillerCfg = @"F:\Application\Unity\fontsource_filler.txt";
    const string CharsetPath = @"F:\Application\Unity\charset.txt";
    const string ReportPath = @"F:\Application\Unity\twobake_report.tsv";
    const string LogPath = @"F:\Application\Unity\twobake_log.txt";
    const string OutAssetPath = "Assets/BakedFonts/KotonohaCreator.asset";

    const int PointSize = 56;
    const int Padding = 10;
    const int AtlasSize = 8192;

    static MethodInfo MI_Pack, MI_Render;

    [MenuItem("Tools/Bake Two Source Font")]
    public static void Bake()
    {
        StringBuilder log = new StringBuilder();
        try
        {
            Resolve();
            log.AppendLine("[TWO] pack=" + (MI_Pack == null ? "MISSING" : "ok") + " render=" + (MI_Render == null ? "MISSING" : "ok"));
            string primary = ReadCfg(PrimaryCfg, "Assets/Fonts/ChillRoundGothic_Regular.otf");
            string filler = ReadCfg(FillerCfg, "Assets/Fonts/ResourceHanRoundedCN-Regular.ttf");
            log.AppendLine("[TWO] primary=" + primary);
            log.AppendLine("[TWO] filler =" + filler);
            log.AppendLine("[TWO] pointSize=" + PointSize + " padding=" + Padding + " atlas=" + AtlasSize);

            string charset = File.ReadAllText(CharsetPath, Encoding.UTF8);
            List<uint> want = new List<uint>();
            HashSet<uint> seen = new HashSet<uint>();
            for (int i = 0; i < charset.Length; i++) { uint u = charset[i]; if (seen.Add(u)) want.Add(u); }
            want.Sort();
            log.AppendLine("[TWO] charset distinct=" + want.Count);

            // ---------- pass 1: primary ----------
            FontEngine.InitializeFontEngine();
            FontEngineError e1 = FontEngine.LoadFontFace(primary, PointSize);
            FontEngine.SetFaceSize(PointSize);
            log.AppendLine("[TWO] load primary -> " + e1);
            Dictionary<uint, uint> gid1 = new Dictionary<uint, uint>();      // cp -> gid
            List<uint> order1 = new List<uint>();
            Dictionary<uint, List<uint>> glyphToChars = new Dictionary<uint, List<uint>>();
            List<uint> missing = new List<uint>();
            for (int i = 0; i < want.Count; i++)
            {
                uint gid = 0; bool ok = false;
                try { ok = FontEngine.TryGetGlyphIndex(want[i], out gid); } catch (Exception) { }
                if (!ok || gid == 0) { missing.Add(want[i]); continue; }
                gid1[want[i]] = gid;
                Add(glyphToChars, gid, want[i]);
            }
            log.AppendLine("[TWO] primary covers=" + gid1.Count + " lacks=" + missing.Count);

            GlyphLoadFlags flags = GlyphLoadFlags.LOAD_RENDER | GlyphLoadFlags.LOAD_NO_HINTING;
            List<GlyphRect> free = new List<GlyphRect>() { new GlyphRect(0, 0, AtlasSize - 1, AtlasSize - 1) };
            List<GlyphRect> used = new List<GlyphRect>();
            List<Glyph> toPack = new List<Glyph>(), packed = new List<Glyph>();
            HashSet<uint> packedGids = new HashSet<uint>();
            LoadGlyphs(gid1, glyphToChars, flags, toPack, packed, packedGids, ref missing);
            int beforePack = toPack.Count;
            MI_Pack.Invoke(null, new object[] { toPack, packed, Padding, GlyphPackingMode.BestShortSideFit,
                GlyphRenderMode.SDFAA, AtlasSize, AtlasSize, free, used });
            log.AppendLine("[TWO] pass1 toPack=" + beforePack + " packed=" + packed.Count + " stillToPack=" + toPack.Count + " freeRects=" + free.Count);

            // ---------- pass 2: filler, only for code points still uncovered ----------
            List<uint> fillCps = new List<uint>();
            foreach (uint u in missing) fillCps.Add(u);
            log.AppendLine("[TWO] filler candidates=" + fillCps.Count);
            int fillerCovered = 0, stillMissing = 0;
            List<Glyph> packed2 = new List<Glyph>();
            if (fillCps.Count > 0)
            {
                FontEngineError e2 = FontEngine.LoadFontFace(filler, PointSize);
                FontEngine.SetFaceSize(PointSize);
                log.AppendLine("[TWO] load filler -> " + e2);
                Dictionary<uint, uint> gid2 = new Dictionary<uint, uint>();
                List<uint> rest = new List<uint>();
                for (int i = 0; i < fillCps.Count; i++)
                {
                    uint gid = 0; bool ok = false;
                    try { ok = FontEngine.TryGetGlyphIndex(fillCps[i], out gid); } catch (Exception) { }
                    if (!ok || gid == 0) { rest.Add(fillCps[i]); continue; }
                    gid2[fillCps[i]] = gid;
                    Add(glyphToChars, gid | 0x80000000u, fillCps[i]);   // separate key space from pass 1
                }
                stillMissing = rest.Count;
                List<Glyph> toPack2 = new List<Glyph>();
                LoadGlyphs(gid2, glyphToChars, flags, toPack2, packed2, packedGids, ref rest, true);
                int before2 = toPack2.Count;
                MI_Pack.Invoke(null, new object[] { toPack2, packed2, Padding, GlyphPackingMode.BestShortSideFit,
                    GlyphRenderMode.SDFAA, AtlasSize, AtlasSize, free, used });
                fillerCovered = packed2.Count;
                log.AppendLine("[TWO] pass2 toPack=" + before2 + " packed=" + packed2.Count + " stillToPack=" + toPack2.Count + " freeRects=" + free.Count);
            }

            // ---------- tables ----------
            List<Glyph> glyphTable = new List<Glyph>();
            List<TMP_Character> charTable = new List<TMP_Character>();
            List<Glyph> toRender1 = new List<Glyph>();
            for (int i = 0; i < packed.Count; i++)
            {
                Glyph g = packed[i];
                glyphTable.Add(g);
                if (g.glyphRect.width > 0 && g.glyphRect.height > 0) toRender1.Add(g);
                List<uint> cs;
                if (glyphToChars.TryGetValue(g.index, out cs))
                    for (int k = 0; k < cs.Count; k++) charTable.Add(new TMP_Character(cs[k], g));
            }
            List<Glyph> toRender2 = new List<Glyph>();
            for (int i = 0; i < packed2.Count; i++)
            {
                Glyph g = packed2[i];
                glyphTable.Add(g);
                if (g.glyphRect.width > 0 && g.glyphRect.height > 0) toRender2.Add(g);
                List<uint> cs;
                if (glyphToChars.TryGetValue(g.index | 0x80000000u, out cs))
                    for (int k = 0; k < cs.Count; k++) charTable.Add(new TMP_Character(cs[k], g));
            }
            log.AppendLine("[TWO] glyphTable=" + glyphTable.Count + " charTable=" + charTable.Count
                + " toRender1=" + toRender1.Count + " toRender2=" + toRender2.Count + " fillerMissing=" + stillMissing);

            // ---------- render + merge ----------
            // CRITICAL: RenderGlyphsToTexture re-renders glyphs BY INDEX from the face that is
            // currently loaded. Pass 2 loaded the filler face, so the primary face MUST be reloaded
            // before rendering pass 1 -- otherwise every shared glyph is drawn with the filler's
            // outlines (i.e. every character becomes a different character).
            byte[] buf = new byte[AtlasSize * AtlasSize];
            FontEngineError e3 = FontEngine.LoadFontFace(primary, PointSize);
            FontEngine.SetFaceSize(PointSize);
            log.AppendLine("[TWO] reload primary before render -> " + e3);
            if (toRender1.Count > 0)
                MI_Render.Invoke(null, new object[] { toRender1, Padding, GlyphRenderMode.SDFAA, buf, AtlasSize, AtlasSize });
            long ink1 = SampleInk(buf);
            if (toRender2.Count > 0)
            {
                FontEngineError e4 = FontEngine.LoadFontFace(filler, PointSize);
                FontEngine.SetFaceSize(PointSize);
                log.AppendLine("[TWO] reload filler before render -> " + e4);
                byte[] buf2 = new byte[AtlasSize * AtlasSize];
                MI_Render.Invoke(null, new object[] { toRender2, Padding, GlyphRenderMode.SDFAA, buf2, AtlasSize, AtlasSize });
                try
                {
                    byte[] ctl = new byte[AtlasSize * AtlasSize];
                    List<Glyph> one = new List<Glyph>() { toRender1[0] };
                    MI_Render.Invoke(null, new object[] { one, Padding, GlyphRenderMode.SDFAA, ctl, AtlasSize, AtlasSize });
                    Glyph g0 = toRender1[0];
                    bool same = true;
                    for (int row = 0; row < g0.glyphRect.height && same; row++)
                    {
                        int s0 = (g0.glyphRect.y + row) * AtlasSize + g0.glyphRect.x;
                        for (int col = 0; col < g0.glyphRect.width; col++)
                            if (buf[s0 + col] != ctl[s0 + col]) { same = false; break; }
                    }
                    log.AppendLine("[TWO] CONTROL pass1-glyph-vs-fillerRender identical=" + same
                        + (same ? "   <-- BUG: pass1 was drawn with the filler face" : "   (good: pass1 used the primary face)"));
                }
                catch (Exception ce) { log.AppendLine("[TWO] control failed: " + ce.Message); }
                long ink2 = SampleInk(buf2);
                int copied = 0;
                for (int i = 0; i < toRender2.Count; i++)
                {
                    Glyph g = toRender2[i];
                    int x = g.glyphRect.x, y = g.glyphRect.y, w = g.glyphRect.width, h = g.glyphRect.height;
                    if (w <= 0 || h <= 0) continue;
                    if (x + w > AtlasSize || y + h > AtlasSize) continue;
                    for (int row = 0; row < h; row++)
                    {
                        int src = (y + row) * AtlasSize + x;
                        Buffer.BlockCopy(buf2, src, buf, src, w);
                    }
                    copied++;
                }
                log.AppendLine("[TWO] filler ink(sampled)=" + ink2 + " glyphsCopied=" + copied);
            }
            log.AppendLine("[TWO] merged ink(sampled)=" + SampleInk(buf) + " (pass1 was " + ink1 + ")");
            File.WriteAllBytes(@"F:\Application\Unity\twobake_atlas.bin", buf);

            // ---------- font asset ----------
            FaceInfo face = FontEngine.GetFaceInfo();
            TMP_FontAsset fa = ScriptableObject.CreateInstance<TMP_FontAsset>();
            AssetDatabase.CreateAsset(fa, OutAssetPath);
            SetProp(fa, "version", "1.1.0");
            SetField(fa, "m_SourceFontFileGUID", AssetDatabase.AssetPathToGUID(primary));
            SetProp(fa, "atlasRenderMode", GlyphRenderMode.SDFAA);
            SetProp(fa, "faceInfo", face);
            SetProp(fa, "glyphTable", glyphTable);
            SetProp(fa, "characterTable", charTable);
            SetProp(fa, "atlasWidth", AtlasSize);
            SetProp(fa, "atlasHeight", AtlasSize);
            SetProp(fa, "atlasPadding", Padding);
            SetProp(fa, "atlasPopulationMode", AtlasPopulationMode.Static);
            SetProp(fa, "usedGlyphRects", used);
            SetProp(fa, "freeGlyphRects", free);
            try { SetProp(fa, "fontFeatureTable", new TMP_FontFeatureTable()); } catch (Exception) { }
            try { SetField(fa, "m_KerningTable", new KerningTable()); } catch (Exception) { }
            try { Invoke(fa, "SortGlyphAndCharacterTables"); } catch (Exception) { }
            try
            {
                Array wt = Array.CreateInstance(typeof(TMP_FontWeightPair), 10);
                FieldInfo rf = typeof(TMP_FontWeightPair).GetField("regularTypeface");
                FieldInfo itf = typeof(TMP_FontWeightPair).GetField("italicTypeface");
                for (int i = 0; i < 10; i++)
                {
                    object pair = Activator.CreateInstance(typeof(TMP_FontWeightPair));
                    if (rf != null) rf.SetValue(pair, fa);
                    if (itf != null) itf.SetValue(pair, fa);
                    wt.SetValue(pair, i);
                }
                SetField(fa, "m_FontWeightTable", wt);
            }
            catch (Exception) { }

            Texture2D tex = new Texture2D(AtlasSize, AtlasSize, TextureFormat.Alpha8, false);
            tex.name = "KotonohaCreator Atlas";
            tex.LoadRawTextureData(buf);
            tex.Apply(false, false);
            SetProp(fa, "atlasTextures", new Texture2D[] { tex });
            AssetDatabase.AddObjectToAsset(tex, fa);

            Shader sh = Shader.Find("TextMeshPro/Distance Field");
            if (sh != null)
            {
                Material mat = new Material(sh);
                mat.name = "KotonohaCreator Material";
                mat.SetTexture(ShaderUtilities.ID_MainTex, tex);
                mat.SetFloat(ShaderUtilities.ID_TextureWidth, AtlasSize);
                mat.SetFloat(ShaderUtilities.ID_TextureHeight, AtlasSize);
                mat.SetFloat(ShaderUtilities.ID_GradientScale, Padding + 1);
                mat.SetFloat(ShaderUtilities.ID_WeightNormal, fa.normalStyle);
                mat.SetFloat(ShaderUtilities.ID_WeightBold, fa.boldStyle);
                SetField(fa, "material", mat);
                AssetDatabase.AddObjectToAsset(mat, fa);
                log.AppendLine("[TWO] material _GradientScale=" + (Padding + 1));
            }
            else log.AppendLine("[TWO] SHADER NOT FOUND");

            try { Invoke(fa, "ReadFontAssetDefinition"); } catch (Exception e) { log.AppendLine("[TWO] ReadFontAssetDefinition: " + Desc(e)); }

            // ---------- report per code point ----------
            Dictionary<uint, Glyph> byGlyph = new Dictionary<uint, Glyph>();
            for (int i = 0; i < glyphTable.Count; i++) byGlyph[glyphTable[i].index] = glyphTable[i];
            StringBuilder rep = new StringBuilder();
            rep.AppendLine("cp\tgid\trect_x\trect_y\trect_w\trect_h\tadv\tstatus");
            int repOk = 0, empty = 0, no = 0;
            for (int i = 0; i < want.Count; i++)
            {
                uint cp = want[i];
                uint gid = 0; bool has = false;
                Glyph g; string status;
                if (gid1.TryGetValue(cp, out gid)) { if (byGlyph.TryGetValue(gid, out g) && g.glyphRect.width > 0) { status = "ok"; repOk++; } else { status = "emptyRect"; empty++; } }
                else if (byGlyph.TryGetValue(gidFor(byGlyph, cp, glyphToChars), out g) && false) { status = "x"; }
                else { status = "noGlyphIndex"; no++; }
                rep.AppendLine("U+" + cp.ToString("X4") + "\t" + gid + "\t" + (status == "ok" ? byGlyph[gid].glyphRect.x.ToString() : "-1")
                    + "\t" + (status == "ok" ? byGlyph[gid].glyphRect.y.ToString() : "-1")
                    + "\t" + (status == "ok" ? byGlyph[gid].glyphRect.width.ToString() : "0")
                    + "\t" + (status == "ok" ? byGlyph[gid].glyphRect.height.ToString() : "0")
                    + "\t" + (status == "ok" ? byGlyph[gid].metrics.horizontalAdvance.ToString("0.###") : "0") + "\t" + status);
            }
            File.WriteAllText(ReportPath, rep.ToString(), new UTF8Encoding(false));
            log.AppendLine("[TWO] report ok=" + repOk + " emptyRect=" + empty + " noGlyphIndex=" + no);
            int rb = -1;
            try { if (fa.characterTable != null) rb = fa.characterTable.Count; } catch (Exception) { }
            log.AppendLine("[TWO] read-back charTable=" + rb);
            EditorUtility.SetDirty(fa);
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            log.AppendLine("[TWO] saved " + OutAssetPath);
        }
        catch (Exception e) { log.AppendLine("[TWO] FATAL " + e); }
        File.WriteAllText(LogPath, log.ToString(), new UTF8Encoding(false));
        Debug.Log("[TWO] log written");
        EditorApplication.Exit(0);
    }

    static uint gidFor(Dictionary<uint, Glyph> byGlyph, uint cp, Dictionary<uint, List<uint>> m) { return 0; }

    static void Add(Dictionary<uint, List<uint>> map, uint key, uint cp)
    {
        List<uint> l;
        if (!map.TryGetValue(key, out l)) { l = new List<uint>(); map[key] = l; }
        l.Add(cp);
    }

    static void LoadGlyphs(Dictionary<uint, uint> gidMap, Dictionary<uint, List<uint>> glyphToChars,
        GlyphLoadFlags flags, List<Glyph> toPack, List<Glyph> packed, HashSet<uint> packedGids, ref List<uint> missing, bool filler = false)
    {
        List<uint> newMissing = new List<uint>();
        foreach (KeyValuePair<uint, uint> kv in gidMap)
        {
            uint key = filler ? (kv.Value | 0x80000000u) : kv.Value;
            if (packedGids.Contains(key)) continue;
            try
            {
                Glyph g;
                if (FontEngine.TryGetGlyphWithIndexValue(kv.Value, flags, out g))
                {
                    if (g.glyphRect.width > 0 && g.glyphRect.height > 0) toPack.Add(g);
                    else packed.Add(g);
                    packedGids.Add(key);
                }
                else newMissing.Add(kv.Key);
            }
            catch (Exception) { newMissing.Add(kv.Key); }
        }
        if (filler) missing = newMissing;
    }

    static long SampleInk(byte[] b)
    {
        long n = 0;
        for (int i = 0; i < b.Length; i += 997) if (b[i] != 0) n++;
        return n;
    }

    static string ReadCfg(string path, string def)
    {
        try { if (File.Exists(path)) { string s = File.ReadAllText(path).Trim(); if (s.Length > 0) return s; } } catch (Exception) { }
        return def;
    }

    static void Resolve()
    {
        MI_Pack = Find("TryPackGlyphsInAtlas", new string[]
        { "List`1<Glyph>", "List`1<Glyph>", "Int32", "GlyphPackingMode", "GlyphRenderMode", "Int32", "Int32", "List`1<GlyphRect>", "List`1<GlyphRect>" });
        MI_Render = Find("RenderGlyphsToTexture", new string[]
        { "List`1<Glyph>", "Int32", "GlyphRenderMode", "Byte[]", "Int32", "Int32" });
    }

    static string Sig(ParameterInfo p)
    {
        Type t = p.ParameterType;
        if (t.IsByRef) t = t.GetElementType();
        if (t.IsGenericType) return t.Name + "<" + t.GetGenericArguments()[0].Name + ">";
        return t.Name;
    }

    static MethodInfo Find(string name, string[] want)
    {
        MethodInfo[] ms = typeof(FontEngine).GetMethods(BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
        for (int i = 0; i < ms.Length; i++)
        {
            if (ms[i].Name != name) continue;
            ParameterInfo[] ps = ms[i].GetParameters();
            if (ps.Length != want.Length) continue;
            bool ok = true;
            for (int k = 0; k < ps.Length; k++) if (Sig(ps[k]) != want[k]) { ok = false; break; }
            if (ok) return ms[i];
        }
        return null;
    }

    static void SetProp(object o, string name, object value)
    {
        PropertyInfo p = o.GetType().GetProperty(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        if (p == null) return;
        MethodInfo setter = p.GetSetMethod(true);
        if (setter != null) setter.Invoke(o, new object[] { value });
    }

    static void SetField(object o, string name, object value)
    {
        FieldInfo f = o.GetType().GetField(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        if (f != null) f.SetValue(o, value);
    }

    static object Invoke(object o, string name)
    {
        MethodInfo m = o.GetType().GetMethod(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        return m == null ? null : m.Invoke(o, null);
    }

    static string Desc(Exception e)
    {
        if (e is TargetInvocationException && e.InnerException != null)
            return e.InnerException.GetType().Name + ": " + e.InnerException.Message;
        return e.GetType().Name + ": " + e.Message;
    }
}
