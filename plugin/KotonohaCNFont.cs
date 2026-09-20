// Kotonoha CN Font Fallback v1.3
// Why this version: creating a TMP font asset at runtime is impossible on this build
//   (v1.0/v1.1: OS fonts -> TryAddCharacters failed for every char; v1.2: embedded fonts -> NRE + crash).
// New mechanism (no glyph rasterisation at all):
//   the game already ships several FULLY BAKED TMP font assets whose coverage is COMPLEMENTARY:
//     * the previous translator's Chinese font  -> covers CJK, lacks ASCII and fullwidth punctuation
//     * the original Japanese fonts             -> cover ASCII + punctuation, lack simplified-only chars
//   TMP's fallback chain is designed exactly for "primary font lacks this glyph".
//   So we simply cross-register the existing assets as each other's fallbacks.
// Safety: no texture allocation, no asset creation, no bulk resource loading.
using System;
using System.Collections;
using System.Collections.Generic;
using BepInEx;
using TMPro;
using UnityEngine;

namespace KotonohaCN
{
    [BepInPlugin("kotonoha.cn.fontfallback", "Kotonoha CN Font Fallback", "1.3.0")]
    public class FontFallbackPlugin : BaseUnityPlugin
    {
        private int _lastTotal = -1;

        private void Awake()
        {
            Logger.LogInfo("[CN] plugin awake v1.3 (cross-link existing font assets); Unity " + Application.unityVersion);
            StartCoroutine(Run());
        }

        private IEnumerator Run()
        {
            yield return new WaitForSeconds(1f);
            while (true)
            {
                Attach();
                yield return new WaitForSeconds(2f);
            }
        }

        private void Attach()
        {
            try
            {
                UnityEngine.Object[] found = Resources.FindObjectsOfTypeAll(typeof(TMP_FontAsset));
                List<TMP_FontAsset> all = new List<TMP_FontAsset>();
                for (int i = 0; i < found.Length; i++)
                {
                    TMP_FontAsset fa = found[i] as TMP_FontAsset;
                    if (fa != null) all.Add(fa);
                }
                if (all.Count < 2) return;

                int added = 0;
                for (int i = 0; i < all.Count; i++)
                {
                    TMP_FontAsset fa = all[i];
                    if (fa.fallbackFontAssetTable == null)
                        fa.fallbackFontAssetTable = new List<TMP_FontAsset>();
                    for (int k = 0; k < all.Count; k++)
                    {
                        if (k == i) continue;
                        if (!fa.fallbackFontAssetTable.Contains(all[k]))
                        {
                            fa.fallbackFontAssetTable.Add(all[k]);
                            added++;
                        }
                    }
                }

                if (added > 0 || all.Count != _lastTotal)
                {
                    _lastTotal = all.Count;
                    Logger.LogInfo("[CN] 已发现 " + all.Count + " 个字体资产，本次新增互链 " + added + " 条");
                    for (int i = 0; i < all.Count; i++)
                    {
                        TMP_FontAsset fa = all[i];
                        int cnt = -1;
                        try { if (fa.characterTable != null) cnt = fa.characterTable.Count; } catch (Exception) { }
                        Logger.LogInfo("[CN]   字体[" + i + "] name=" + fa.name
                            + " 字符数=" + cnt
                            + " 回退数=" + (fa.fallbackFontAssetTable == null ? -1 : fa.fallbackFontAssetTable.Count));
                    }
                }
            }
            catch (Exception e) { Logger.LogWarning("[CN] 互链失败: " + e.Message); }
        }
    }
}
