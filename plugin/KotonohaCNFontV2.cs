// Kotonoha CN Font v3.0 -- runtime font swap + per-original-font proxies.
//
// Why proxies: replacing all five game fonts with one baked font changes more than glyph coverage.
//   * TMP derives sizing from faceInfo.pointSize/scale and line spacing from faceInfo.lineHeight
//     (rendered lineHeight = faceInfo.lineHeight * fontSize / pointSize * scale), so a different
//     lineHeight/ascent/descent changes wrapping, vertical alignment and can clip text in boxes
//     that were sized for the original font.
//   * Each original font also had its own material (per-language presets: outline/glow/etc).
// So for every ORIGINAL font still loaded in the scene we build a proxy:
//   proxy = Instantiate(ourFont)                     // shares the atlas texture + glyph tables
//   proxy.faceInfo = original.faceInfo rescaled by k = ourPointSize/origPointSize * origScale
//   proxy.normalStyle/boldStyle/... copied from the original
//   proxy.material = copy of the original material with atlas-bound properties kept OURS
//     (_MainTex/_TextureWidth/_TextureHeight/_GradientScale stay ours; the rest is inherited)
// Texts keep their original font's metrics and look, and we still ship ONE 8192x8192 atlas.
//
// Safety: if anything about the original looks unusable (pointSize/lineHeight <= 0) or a proxy
// cannot be built, the text gets the base baked font -- i.e. the v2.0 behaviour, which is known
// to work in-game.
//
// Diagnostics kept from v2.1: [FACE] inventory of every loaded TMP_FontAsset, [GAP] per-text
// characters our font does NOT contain, pre-swap font usage counts.
//
// ASCII-only source on purpose.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using BepInEx;
using TMPro;
using UnityEngine;
using UnityEngine.TextCore;

namespace KotonohaCN
{
    [BepInPlugin("kotonoha.cn.font", "Kotonoha CN Font", "3.0.0")]
    public class FontSwapPlugin : BaseUnityPlugin
    {
        private TMP_FontAsset _font;
        private AssetBundle _bundle;
        private readonly Dictionary<int, TMP_FontAsset> _proxyByOriginal = new Dictionary<int, TMP_FontAsset>();
        private readonly HashSet<int> _ourFontIds = new HashSet<int>();
        private int _lastTotal = -1;
        private int _lastSwapped = -1;
        private bool _inventoryDone;
        private int _gapReports;
        private int _proxyLogs;
        private int _textLogs;
        private int _unknownFontLogs;
        // the game's own font atlases: any material still sampling one of these would show
        // garbled glyphs, because our proxies' glyph rects live in OUR atlas.
        private readonly HashSet<int> _originalAtlases = new HashSet<int>();
        private readonly Dictionary<long, Material> _retargeted = new Dictionary<long, Material>();
        private int _retargetLogs;
        private readonly Dictionary<int, int> _textHash = new Dictionary<int, int>();
        private readonly Dictionary<string, int> _fontUsage = new Dictionary<string, int>();

        private void Awake()
        {
            Logger.LogInfo("[CN] FontSwap v3.0 awake; Unity " + Application.unityVersion
                + " 32bit=" + (IntPtr.Size == 4));
            try { LoadBundle(); }
            catch (Exception e) { Logger.LogError("[CN] bundle load exception: " + e); }

            if (_font != null) StartCoroutine(Loop());
            else Logger.LogError("[CN] no font loaded -> plugin inert");
        }

        private void LoadBundle()
        {
            string dir = Path.GetDirectoryName(Info.Location);
            string[] candidates = new string[]
            {
                Path.Combine(dir, "kotonoha_font.bundle"),
                Path.Combine(dir, "kotonoha_font"),
                Path.Combine(dir, "font.bundle")
            };
            string path = null;
            for (int i = 0; i < candidates.Length; i++)
                if (path == null && File.Exists(candidates[i])) path = candidates[i];
            if (path == null) { Logger.LogError("[CN] bundle file not found next to the plugin dll"); return; }

            _bundle = AssetBundle.LoadFromFile(path);
            if (_bundle == null) { Logger.LogError("[CN] AssetBundle.LoadFromFile returned null"); return; }

            string[] names = _bundle.GetAllAssetNames();
            Logger.LogInfo("[CN] bundle=" + Path.GetFileName(path) + " assets=" + names.Length);
            for (int i = 0; i < names.Length; i++)
            {
                try
                {
                    TMP_FontAsset fa = _bundle.LoadAsset<TMP_FontAsset>(names[i]);
                    if (fa != null) { _font = fa; break; }
                }
                catch (Exception e) { Logger.LogWarning("[CN] load asset failed: " + e.Message); }
            }
            if (_font == null) { Logger.LogError("[CN] no TMP_FontAsset inside bundle"); return; }

            int cnt = -1;
            try { if (_font.characterTable != null) cnt = _font.characterTable.Count; } catch (Exception) { }
            Logger.LogInfo("[CN] loaded font='" + _font.name + "' chars=" + cnt
                + " atlas=" + _font.atlasWidth + "x" + _font.atlasHeight);
            try
            {
                _font.ReadFontAssetDefinition();
                Logger.LogInfo("[CN] characterLookupTable=" + _font.characterLookupTable.Count);
                _ourFontIds.Add(_font.GetInstanceID());
                LogFace("OURS", _font);
            }
            catch (Exception e) { Logger.LogWarning("[CN] ReadFontAssetDefinition failed: " + e); }
        }

        private void LogFace(string label, TMP_FontAsset fa)
        {
            try
            {
                var fi = fa.faceInfo;
                Logger.LogInfo(string.Format(
                    "[FACE] {0} name='{1}' chars={2} atlas={3}x{4} pointSize={5} scale={6} ascent={7:0.###} descent={8:0.###} baseline={9:0.###} capLine={10:0.###} lineHeight={11:0.###} tabWidth={12:0.###} normal={13:0.###} bold={14:0.###}",
                    label, fa.name,
                    (fa.characterTable == null ? -1 : fa.characterTable.Count),
                    fa.atlasWidth, fa.atlasHeight,
                    fi.pointSize, fi.scale, fi.ascentLine, fi.descentLine, fi.baseline, fi.capLine, fi.lineHeight, fi.tabWidth,
                    fa.normalStyle, fa.boldStyle));
            }
            catch (Exception e) { Logger.LogWarning("[CN] LogFace failed: " + e.Message); }
        }

        // ---------------------------------------------------------------- inventory + proxies
        private void Inventory()
        {
            _inventoryDone = true;
            try
            {
                UnityEngine.Object[] fonts = Resources.FindObjectsOfTypeAll(typeof(TMP_FontAsset));
                Logger.LogInfo("[CN] TMP_FontAsset objects loaded = " + fonts.Length);
                for (int i = 0; i < fonts.Length; i++)
                {
                    TMP_FontAsset fa = fonts[i] as TMP_FontAsset;
                    if (fa == null) continue;
                    LogFace("GAME[" + i + "]", fa);
                    if (ReferenceEquals(fa, _font)) continue;   // our own font is NOT an "original"
                    try { if (fa.atlasTexture != null) _originalAtlases.Add(fa.atlasTexture.GetInstanceID()); }
                    catch (Exception) { }
                    if (ReferenceEquals(fa, _font)) continue;
                    if (_proxyByOriginal.ContainsKey(fa.GetInstanceID())) continue;
                    TMP_FontAsset proxy = BuildProxy(fa);
                    if (proxy != null) _proxyByOriginal[fa.GetInstanceID()] = proxy;
                }
            }
            catch (Exception e) { Logger.LogWarning("[CN] font inventory failed: " + e.Message); }
        }

        private TMP_FontAsset BuildProxy(TMP_FontAsset orig)
        {
            try
            {
                var of = orig.faceInfo;
                float ourPoint = _font.faceInfo.pointSize;
                float ourScale = _font.faceInfo.scale;
                if (ourPoint <= 0) ourPoint = 64f;
                if (ourScale <= 0) ourScale = 1f;
                if (of.pointSize <= 0 || of.lineHeight <= 0)
                {
                    Logger.LogWarning("[CN] proxy skipped for '" + orig.name + "' (pointSize=" + of.pointSize + " lineHeight=" + of.lineHeight + ")");
                    return null;
                }

                TMP_FontAsset p = UnityEngine.Object.Instantiate(_font);
                p.name = "KotonohaProxy_" + orig.name;
                // ratio that reproduces the original's proportional metrics in OUR point-size space
                float k = (ourPoint / of.pointSize) * (of.scale <= 0 ? 1f : of.scale);
                var nf = _font.faceInfo;   // start from ours (pointSize/scale must stay ours)
                nf.ascentLine = of.ascentLine * k;
                nf.descentLine = of.descentLine * k;
                nf.baseline = of.baseline * k;
                nf.capLine = of.capLine * k;
                nf.meanLine = of.meanLine * k;
                nf.lineHeight = of.lineHeight * k;
                nf.tabWidth = of.tabWidth * k;
                nf.underlineOffset = of.underlineOffset * k;
                nf.underlineThickness = of.underlineThickness * k;
                nf.strikethroughOffset = of.strikethroughOffset * k;
                SetFace(p, nf);
                p.normalStyle = orig.normalStyle;
                p.boldStyle = orig.boldStyle;
                p.normalSpacingOffset = orig.normalSpacingOffset;
                p.boldSpacing = orig.boldSpacing;
                p.italicStyle = orig.italicStyle;
                p.tabSize = orig.tabSize;
                p.material = BuildMaterial(orig);
                p.ReadFontAssetDefinition();
                NormalizeAdvances(p, orig);
                _ourFontIds.Add(p.GetInstanceID());

                if (_proxyLogs < 12)
                {
                    _proxyLogs++;
                    Logger.LogInfo(string.Format(
                        "[PROXY] '{0}' -> '{1}' k={2:0.####} lineHeight {3:0.###}->{4:0.###} ascent {5:0.###}->{6:0.###} descent {7:0.###}->{8:0.###} material='{9}'",
                        orig.name, p.name, k, of.lineHeight, nf.lineHeight, of.ascentLine, nf.ascentLine,
                        of.descentLine, nf.descentLine, p.material == null ? "null" : p.material.name));
                    LogFace("PROXY", p);
                }
                return p;
            }
            catch (Exception e)
            {
                Logger.LogWarning("[CN] BuildProxy failed for '" + orig.name + "': " + e.Message);
                return null;
            }
        }

        // Properties that MUST stay ours (they bind the material to our atlas / its SDF spread).
        private static readonly HashSet<string> KeepOurs = new HashSet<string>()
        {
            "_MainTex", "_TextureWidth", "_TextureHeight", "_GradientScale",
            "_ScaleRatioA", "_ScaleRatioB", "_ScaleRatioC", "_ClipRect", "_UseUIAlphaClip"
        };

        // TMP's SDF shader properties that carry the original look (colour / outline / underlay /
        // glow / bevel). Shader property enumeration is not available to a runtime plugin in 2019.1,
        // so the names are listed explicitly.
        private static readonly string[] InheritFloats = new string[]
        {
            "_FaceDilate", "_OutlineWidth", "_OutlineSoftness",
            "_UnderlayOffsetX", "_UnderlayOffsetY", "_UnderlayDilate", "_UnderlaySoftness",
            "_WeightNormal", "_WeightBold", "_VertexOffsetX", "_VertexOffsetY",
            "_PerspectiveFilter", "_Sharpness", "_ScaleX", "_ScaleY",
            "_Bevel", "_BevelOffset", "_BevelWidth", "_BevelClamp", "_BevelRoundness",
            "_LightAngle", "_SpecularPower", "_Reflectivity", "_Diffuse", "_Ambient",
            "_GlowOffset", "_GlowInner", "_GlowOuter", "_GlowPower", "_GlowClipping",
            "_Stencil", "_StencilComp", "_StencilOp", "_StencilWriteMask", "_StencilReadMask",
            "_ColorMask", "_CullMode"
        };

        private static readonly string[] InheritColors = new string[]
        {
            "_FaceColor", "_OutlineColor", "_UnderlayColor",
            "_SpecularColor", "_ReflectFaceColor", "_ReflectOutlineColor", "_GlowColor"
        };

        // A per-proxy material that keeps OUR atlas binding but inherits the original font's look.
        // This is what was making every string render pure white: a fresh Material() has no
        // _FaceColor / outline / keywords from the game's per-language material presets.
        private Material BuildMaterial(TMP_FontAsset orig)
        {
            Material m = new Material(_font.material);
            m.name = "KotonohaProxy_" + orig.name + " Material";
            Material src = orig.material;
            if (src == null) return m;
            try
            {
                int nf = 0, nc = 0;
                for (int i = 0; i < InheritFloats.Length; i++)
                {
                    string p = InheritFloats[i];
                    if (KeepOurs.Contains(p)) continue;
                    if (!src.HasProperty(p) || !m.HasProperty(p)) continue;
                    m.SetFloat(p, src.GetFloat(p));
                    nf++;
                }
                for (int i = 0; i < InheritColors.Length; i++)
                {
                    string p = InheritColors[i];
                    if (KeepOurs.Contains(p)) continue;
                    if (!src.HasProperty(p) || !m.HasProperty(p)) continue;
                    m.SetColor(p, src.GetColor(p));
                    nc++;
                }
                // effect keywords (OUTLINE_ON, UNDERLAY_ON, GLOW_ON, BEVEL_ON, ...) must come along,
                // otherwise an outline/glow material renders as if the effect were off
                string[] kw = src.shaderKeywords;
                if (kw != null && kw.Length > 0) m.shaderKeywords = kw;
                if (_proxyLogs < 12)
                    Logger.LogInfo("[MAT] inherited from '" + src.name + "': floats=" + nf + " colors=" + nc
                        + " keywords=" + (kw == null ? 0 : kw.Length)
                        + " faceColor=" + (src.HasProperty("_FaceColor") ? src.GetColor("_FaceColor").ToString() : "n/a"));
            }
            catch (Exception e) { Logger.LogWarning("[CN] material inherit failed: " + e.Message); }
            return m;
        }

        // The original fonts may have NARROWER advances than our 1.0 em CJK, which makes text wrap
        // in boxes that were sized for them ("强制换行"). Measure the em-relative advance of a few
        // common hanzi in BOTH fonts and scale our glyph advances by that ratio -- self-calibrating,
        // no manual data needed. Glyph SIZE is untouched (that comes from pointSize/scale).
        private void NormalizeAdvances(TMP_FontAsset p, TMP_FontAsset orig)
        {
            try
            {
                uint[] probe = new uint[] { 0x4E00, 0x56FD, 0x65E5, 0x672C, 0x5927, 0x4EBA, 0x5B57 };
                float ratio = -1f;
                uint used = 0;
                for (int i = 0; i < probe.Length && ratio <= 0f; i++)
                {
                    uint u = probe[i];
                    TMP_Character oc, pc;
                    if (!orig.characterLookupTable.TryGetValue(u, out oc)) continue;
                    if (!p.characterLookupTable.TryGetValue(u, out pc)) continue;
                    float op = Mathf.Max(1f, orig.faceInfo.pointSize);
                    float np = Mathf.Max(1f, p.faceInfo.pointSize);
                    float o = oc.glyph.metrics.horizontalAdvance / op;
                    float n = pc.glyph.metrics.horizontalAdvance / np;
                    if (o > 0.1f && n > 0.1f) { ratio = o / n; used = u; }
                }
                float gsOrig = (orig.material != null && orig.material.HasProperty("_GradientScale")) ? orig.material.GetFloat("_GradientScale") : -1f;
                float gsOurs = (p.material != null && p.material.HasProperty("_GradientScale")) ? p.material.GetFloat("_GradientScale") : -1f;
                if (ratio <= 0f)
                {
                    Logger.LogInfo("[ADV] '" + orig.name + "' no shared probe glyph (origPoint=" + orig.faceInfo.pointSize
                        + " gradientScale orig=" + gsOrig + " ours=" + gsOurs + ")");
                    return;
                }
                if (Mathf.Abs(ratio - 1f) < 0.02f)
                {
                    Logger.LogInfo("[ADV] '" + orig.name + "' advanceRatio=" + ratio.ToString("0.####") + " (U+" + used.ToString("X4")
                        + ") -> no change; gradientScale orig=" + gsOrig + " ours=" + gsOurs);
                    return;
                }
                List<Glyph> gt = p.glyphTable;
                for (int i = 0; i < gt.Count; i++)
                {
                    Glyph g = gt[i];
                    GlyphMetrics m = g.metrics;
                    m.horizontalAdvance *= ratio;
                    g.metrics = m;
                    gt[i] = g;
                }
                p.ReadFontAssetDefinition();
                Logger.LogInfo("[ADV] '" + orig.name + "' advanceRatio=" + ratio.ToString("0.####") + " (from U+" + used.ToString("X4")
                    + ") applied to " + gt.Count + " glyphs; gradientScale orig=" + gsOrig + " ours=" + gsOurs);
            }
            catch (Exception e) { Logger.LogWarning("[CN] NormalizeAdvances failed for '" + orig.name + "': " + e.Message); }
        }

        private static void SetFace(TMP_FontAsset fa, UnityEngine.TextCore.FaceInfo face)
        {
            PropertyInfo p = typeof(TMP_FontAsset).GetProperty("faceInfo",
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            if (p == null) return;
            MethodInfo setter = p.GetSetMethod(true);
            if (setter != null) setter.Invoke(fa, new object[] { face });
        }

        // ---------------------------------------------------------------- main loop
        private IEnumerator Loop()
        {
            yield return new WaitForSeconds(0.2f);
            while (true)
            {
                Swap();
                // was 1s: new text appeared showing the ORIGINAL font first (garbled), then snapped
                // to ours. 0.15s makes that window a single frame.
                yield return new WaitForSeconds(0.15f);
            }
        }

        private void Swap()
        {
            try
            {
                UnityEngine.Object[] objs = Resources.FindObjectsOfTypeAll(typeof(TMP_Text));
                if (!_inventoryDone && objs.Length > 0) Inventory();

                int total = 0;
                int swapped = 0;
                int proxied = 0;
                for (int i = 0; i < objs.Length; i++)
                {
                    TMP_Text t = objs[i] as TMP_Text;
                    if (t == null) continue;
                    total++;
                    if (t.font != null && _ourFontIds.Contains(t.font.GetInstanceID()))
                    {
                        // the game may re-assign its own material afterwards -> keep rebinding it
                        FixMaterial(t, t.fontSharedMaterial);
                        CheckText(t);
                        continue;
                    }

                    TMP_FontAsset target = _font;
                    try
                    {
                        string before = t.font == null ? "(null)" : t.font.name;
                        int n;
                        _fontUsage.TryGetValue(before, out n);
                        _fontUsage[before] = n + 1;

                        // A font can be loaded AFTER the initial inventory (the menu loads
                        // GDhwGoJA-OTF112b2 lazily). Build its proxy on demand, otherwise those
                        // texts would fall back to the base font -> wrong line metrics (wrapping!)
                        if (t.font != null && !ReferenceEquals(t.font, _font)
                            && !_proxyByOriginal.ContainsKey(t.font.GetInstanceID()))
                        {
                            TMP_FontAsset late = BuildProxy(t.font);
                            if (late != null)
                            {
                                _proxyByOriginal[t.font.GetInstanceID()] = late;
                                Logger.LogInfo("[PROXY+] late proxy for '" + t.font.name + "'");
                            }
                        }

                        TMP_FontAsset proxy;
                        if (t.font != null && _proxyByOriginal.TryGetValue(t.font.GetInstanceID(), out proxy))
                        {
                            target = proxy;
                            proxied++;
                        }
                        else if (t.font != null && !ReferenceEquals(t.font, _font) && _unknownFontLogs < 10)
                        {
                            _unknownFontLogs++;
                            Logger.LogWarning("[FONT] text uses a font with no proxy: '" + before + "' -> base font");
                        }
                        if (_textLogs < 30 && !string.IsNullOrEmpty(t.text))
                        {
                            _textLogs++;
                            string sample = t.text.Replace("\n", "\\n");
                            if (sample.Length > 28) sample = sample.Substring(0, 28);
                            Logger.LogInfo("[TEXT] #" + _textLogs + " orig='" + before + "' -> '" + target.name
                                + "' size=" + t.fontSize + " wrap=" + t.enableWordWrapping
                                + " prefW=" + (int)t.preferredWidth + " boxW=" + (int)t.rectTransform.rect.width
                                + " text='" + sample + "'");
                        }
                        // IMPORTANT: grab the game's material BEFORE t.font is re-assigned, because
                        // that assignment immediately swaps m_sharedMaterial to our own. The panel's
                        // outline/colour live in THIS material, not in the font asset's material.
                        Material prev = t.fontSharedMaterial;
                        t.font = target;
                        FixMaterial(t, prev);
                        swapped++;
                    }
                    catch (Exception e) { Logger.LogWarning("[CN] assign failed: " + e.Message); }
                    CheckText(t);
                }

                if (swapped > 0 || total != _lastTotal || swapped != _lastSwapped)
                {
                    _lastTotal = total;
                    _lastSwapped = swapped;
                    Logger.LogInfo("[CN] TMP_Text total=" + total + " swapped=" + swapped
                        + " viaProxy=" + proxied + " proxies=" + _proxyByOriginal.Count);
                    if (swapped == 0 && _fontUsage.Count > 0)
                        foreach (KeyValuePair<string, int> kv in _fontUsage)
                            Logger.LogInfo("[CN]   pre-swap font usage: '" + kv.Key + "' x" + kv.Value);
                }
            }
            catch (Exception e) { Logger.LogWarning("[CN] swap pass failed: " + e.Message); }
        }

        // Rebind the panel's own material onto OUR atlas while inheriting its look.
        // `prev` is the material the text had before we swapped the font -- that is the one carrying
        // the panel's outline / colours / effect keywords. Keeping _MainTex ours is what stops the
        // garbling (glyph rects come from our atlas but the old material still sampled the old one).
        private void FixMaterial(TMP_Text t, Material prev)
        {
            try
            {
                if (prev == null) return;
                TMP_FontAsset f = t.font;
                if (f == null || f.material == null) return;
                if (prev.GetInstanceID() == f.material.GetInstanceID()) return;
                if (_retargeted.ContainsValue(prev)) return;   // already one of our copies

                long key = ((long)f.GetInstanceID() << 32) ^ (uint)prev.GetInstanceID();
                Material c;
                if (!_retargeted.TryGetValue(key, out c))
                {
                    c = new Material(f.material);          // our atlas / texture size / gradient scale
                    c.name = f.name + " Material (from " + prev.name + ")";
                    int nf = 0, nc = 0;
                    for (int i = 0; i < InheritFloats.Length; i++)
                    {
                        string p = InheritFloats[i];
                        if (KeepOurs.Contains(p) || !prev.HasProperty(p) || !c.HasProperty(p)) continue;
                        c.SetFloat(p, prev.GetFloat(p)); nf++;
                    }
                    for (int i = 0; i < InheritColors.Length; i++)
                    {
                        string p = InheritColors[i];
                        if (KeepOurs.Contains(p) || !prev.HasProperty(p) || !c.HasProperty(p)) continue;
                        c.SetColor(p, prev.GetColor(p)); nc++;
                    }
                    string[] kw = prev.shaderKeywords;
                    if (kw != null && kw.Length > 0) c.shaderKeywords = kw;
                    _retargeted[key] = c;
                    if (_retargetLogs < 12)
                    {
                        _retargetLogs++;
                        string face = prev.HasProperty("_FaceColor") ? prev.GetColor("_FaceColor").ToString() : "n/a";
                        string ow = prev.HasProperty("_OutlineWidth") ? prev.GetFloat("_OutlineWidth").ToString("0.###") : "n/a";
                        Logger.LogInfo("[RETARGET] '" + prev.name + "' -> '" + c.name + "' floats=" + nf + " colors=" + nc
                            + " keywords=" + (kw == null ? 0 : kw.Length) + " faceColor=" + face + " outlineWidth=" + ow);
                    }
                }
                t.fontSharedMaterial = c;
            }
            catch (Exception e) { Logger.LogWarning("[CN] FixMaterial failed: " + e.Message); }
        }

        private void CheckText(TMP_Text t)
        {
            try
            {
                string s = t.text;
                if (string.IsNullOrEmpty(s)) return;

                // 2026-09-13：把"短文本去折行"放到文本变化去重**之前**。实测首次看到某文本时
                // textInfo.lineCount 常为 0（尚未排版），只在文本变化时检查会漏掉真正折行的标签。
                AutoFixWrap(t, s);

                int h = s.GetHashCode();
                int prev;
                if (_textHash.TryGetValue(t.GetInstanceID(), out prev) && prev == h) return;
                _textHash[t.GetInstanceID()] = h;

                // ---- 2026-09-12 新增：短文本强制一行 + 关键文本布局诊断 ----
                // 1) 「敌人」「恢复默认设置」这类短标签在窄方框里会被折成两行；短文本（<=8 字、无空白）
                //    一旦 preferredWidth 超出方框宽度就关掉自动换行，让它和别的文字一样一行显示完。
                // 2) 关键文本（敌人/恢复默认/退出/是否/金）打印 font/material/方框/preferred/行距/
                //    描边宽度，用于把「金币描边偏重」「退出确认重叠」精确定位到具体材质。
                try
                {
                    RectTransform rt = t.rectTransform;
                    if (rt != null)
                    {
                        float boxW = rt.rect.width;
                        float boxH = rt.rect.height;
                        float prefW = t.preferredWidth;
                        // 2026-09-12 实测修正：① '<i>敌人</i>' 带 TMP 标签（s.Length=9）被 8 字门槛挡掉
                        //   -> 先去标签再数"可见字符"；② 首次看到时 textInfo.lineCount 可能为 0（尚未排版）
                        //   -> 用 prefW > boxW 兜底（实测该判据对短标签有效：prefW=80 boxW=50）。
                        int lines = (t.textInfo == null) ? 0 : t.textInfo.lineCount;
                        int vis = 0; bool ws = false; bool numeric = true;
                        for (int k = 0; k < s.Length; k++)
                        {
                            char c = s[k];
                            if (c == '<') { while (k < s.Length && s[k] != '>') k++; continue; }
                            if (c == '\n' || c == '\r' || c == '\t' || c == '\u200B' || c == ' ') { ws = true; break; }
                            vis++;
                            if (!(char.IsDigit(c) || c == '.' || c == ',' || c == '%' || c == 'G' || c == '+' || c == '-'))
                                numeric = false;
                        }
                        Material mcur = t.fontSharedMaterial;
                        float owF = (mcur != null && mcur.HasProperty("_OutlineWidth"))
                            ? mcur.GetFloat("_OutlineWidth") : -1f;
                        bool interesting = s.Contains("敌人") || s.Contains("恢复默认") || s.Contains("退出")
                            || s.Contains("是否") || s.Contains("金") || s.Contains("游戏")
                            || (vis <= 10 && lines > 1) || (numeric && vis >= 1 && vis <= 8)
                            || owF >= 0.1f || (t.preferredHeight > boxH + 1f);
                        if (interesting)
                        {
                            Material m = t.fontSharedMaterial;
                            string ow = (m != null && m.HasProperty("_OutlineWidth"))
                                ? m.GetFloat("_OutlineWidth").ToString("0.###") : "n/a";
                            string fd = (m != null && m.HasProperty("_FaceDilate"))
                                ? m.GetFloat("_FaceDilate").ToString("0.###") : "n/a";
                            Logger.LogInfo("[LAYOUT] text='" + s.Replace("\n", "\\n") + "'"
                                + " font=" + (t.font == null ? "(null)" : t.font.name)
                                + " mat='" + (m == null ? "(null)" : m.name) + "'"
                                + " outlineW=" + ow + " faceDilate=" + fd
                                + " size=" + t.fontSize + " wrap=" + t.enableWordWrapping
                                + " boxW=" + (int)boxW + " boxH=" + (int)boxH
                                + " prefW=" + (int)prefW + " prefH=" + (int)t.preferredHeight
                                + " lineSpacing=" + t.lineSpacing + " lines=" + lines + " chars=" + s.Length);
                        }
                    }
                }
                catch (Exception) { }

                if (_gapReports >= 40) return;

                StringBuilder gaps = new StringBuilder();
                int nGap = 0;
                for (int i = 0; i < s.Length; i++)
                {
                    char c = s[i];
                    if (c == '\n' || c == '\r' || c == '\t' || c == '\u200B' || c == '\u2060') continue;
                    bool has;
                    try { has = _font.HasCharacter(c); } catch (Exception) { break; }
                    if (!has) { nGap++; if (gaps.Length < 60) gaps.Append(c); }
                }
                if (nGap > 0)
                {
                    _gapReports++;
                    string head = s.Length > 40 ? s.Substring(0, 40) : s;
                    Logger.LogWarning("[GAP] font lacks " + nGap + " char(s) [" + gaps.ToString()
                        + "] in text: " + head.Replace("\n", "\\n"));
                }
            }
            catch (Exception) { }
        }

        // ---- 2026-09-13 方案B：按文本内容的白/黑名单 ----
        // 白名单：这些文本一律强制单行（短 UI 标签；玩家反馈过的折行项都列在这里）。
        private static readonly string[] WrapForce = new string[]
        {
            "敌人", "退出", "设置", "图库", "恢复默认", "确定键", "按钮", "显示方式",
            "最高品质", "BGM音量", "持有数量", "是否", "返回", "继续", "关闭", "取消", "确定",
            "薄荷巧克力色的翅膀",
        };
        // 黑名单：这些文本（按子串匹配）永远不强制单行——长物品名/描述本来就该折行。
        private static readonly string[] WrapKeep = new string[]
        {
            "薄荷", "翅膀", "说明", "效果", "描述",
        };

        // 短文本去折行：白名单强制；黑名单豁免；其余用保守启发式（可见 <=6 字 或 方框只有一行高）。
        // 每次轮询都跑（不受文本变化去重影响），因为首次看到时 textInfo.lineCount 可能还是 0。
        private void AutoFixWrap(TMP_Text t, string s)
        {
            try
            {
                if (!t.enableWordWrapping) return;
                RectTransform rt = t.rectTransform;
                if (rt == null || rt.rect.width <= 1f) return;
                int vis = 0;
                for (int k = 0; k < s.Length; k++)
                {
                    char c = s[k];
                    if (c == '<') { while (k < s.Length && s[k] != '>') k++; continue; }
                    if (c == '\n' || c == '\r') return;         // 多行文本是设计意图，不碰
                    if (!char.IsWhiteSpace(c)) vis++;
                }
                if (vis < 1 || vis > 16) return;

                bool force = false;
                for (int i = 0; i < WrapForce.Length; i++)
                    if (s.IndexOf(WrapForce[i]) >= 0) { force = true; break; }
                if (!force)                                      // 白名单优先：明确要求单行的文本不受黑名单限制
                {
                    for (int i = 0; i < WrapKeep.Length; i++)
                        if (s.IndexOf(WrapKeep[i]) >= 0) return;
                }

                int lines = (t.textInfo == null) ? 0 : t.textInfo.lineCount;
                float boxW = rt.rect.width;
                float boxH = rt.rect.height;
                bool overflow = t.preferredWidth > boxW + 1f;

                // 2026-09-13 A方案 ① 溢出报告：横向/纵向放不下，或短文本被折行 → 打 [OVERFLOW]，
                // 这样我一次就能从日志抓到"标签溢出"清单（含 boxW/boxH/prefW/prefH/lines）。
                if (overflow || t.preferredHeight > boxH + 1f || (vis <= 16 && lines > 1))
                {
                    Material mo = t.fontSharedMaterial;
                    Logger.LogInfo("[OVERFLOW] text='" + s.Replace("\n", "\\n") + "' vis=" + vis
                        + " lines=" + lines + " size=" + t.fontSize
                        + " boxW=" + (int)boxW + " boxH=" + (int)boxH
                        + " prefW=" + (int)t.preferredWidth + " prefH=" + (int)t.preferredHeight
                        + " mat='" + (mo == null ? "(null)" : mo.name) + "'");
                }

                // 2026-09-13 A方案 ② 自动缩字：短标签横向溢出 → 把字号缩到"一行刚好放下"，
                // 下限 70%（Mathf.Clamp）且不低于 12px；缩放差 <0.01 视为已收敛（避免反复缩小）。
                if (overflow && vis <= 8 && !force)
                {
                    float ratio = Mathf.Clamp((boxW - 2f) / Mathf.Max(1f, t.preferredWidth), 0.7f, 1f);
                    float target = Mathf.Max(12f, t.fontSize * ratio);
                    if (target < t.fontSize - 0.01f)
                    {
                        Logger.LogInfo("[SHRINK] '" + s + "' size " + t.fontSize.ToString("0.#")
                            + " -> " + target.ToString("0.#") + " (vis=" + vis
                            + " prefW=" + (int)t.preferredWidth + " boxW=" + (int)boxW + ")");
                        t.fontSize = target;
                        return;                                  // 缩字后一行可放下，无需再关换行
                    }
                }
                bool veryShort = vis <= 6;
                bool oneLineBox = boxH < 1.2f * t.fontSize;
                bool want = force ? (vis <= 16) : ((lines > 1 || overflow) && (veryShort || oneLineBox));
                if (!want) return;

                t.enableWordWrapping = false;
                Logger.LogInfo("[WRAPFIX] '" + s + "' vis=" + vis + " lines=" + lines
                    + " prefW=" + (int)t.preferredWidth + " boxW=" + (int)boxW
                    + " force=" + force + " -> enableWordWrapping=false");
            }
            catch (Exception) { }
        }
    }
}
