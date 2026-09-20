#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文本层缺字分析（纯离线，不依赖任何运行时机制）。

做三件事：
  1. 从补丁的 resources.assets 里取出 489 个剧本，按「语言标签」分组统计用到的字符
     （剧本格式：<main><japan>...  下一行为 <台词载荷>；语言标签 = japan/raysant/spirit/other）
  2. 从 sharedassets0.assets / resources.assets 里取出每个 TMP 字体资产已烘焙的字符集
  3. 逐语言标签 × 逐字体输出「缺字」清单，并给出全局缺字（任何字体都没有的字）

输出:
  _hanhua/out/cov_report.txt          人类可读报告
  _hanhua/out/lang_<lang>.txt         每个语言标签用到的字符集
  _hanhua/out/missing_all_fonts.txt   所有字体都没有的字（必然显示为方块）
用法: python analyze_coverage.py
"""
import os, sys, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
import parse_tmp_font as PTF
from netmeta import PE, parse_us

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
RES = os.path.join(ROOT, 'kotonoha_Data', 'resources.assets')
SA0 = os.path.join(ROOT, 'kotonoha_Data', 'sharedassets0.assets')
DLL = os.path.join(ROOT, 'kotonoha_Data', 'Managed', 'Assembly-CSharp.dll')
OUT = os.path.join(ROOT, '_hanhua', 'out')

LANGS = ('japan', 'raysant', 'spirit', 'other')
MAIN_RE = re.compile(r'<main>(?:<([a-zA-Z]+)>)?')


def load_scripts():
    f = UnityFile(RES, verbose=False)
    return f, f.textassets()


def split_lang(text):
    """把剧本按 <main><lang> 命令行切分，返回 {lang: 字符集合}"""
    per = dict((l, set()) for l in LANGS)
    per['(未标注)'] = set()
    cur = None
    lines = text.split('\n')
    for ln in lines:
        s = ln.strip()
        if s.startswith('<main>'):
            m = MAIN_RE.match(s)
            tag = (m.group(1) or '').lower() if m else ''
            cur = tag if tag in LANGS else '(未标注)'
            continue
        if s.startswith('<') and s.endswith('>') and len(s) > 2:
            if cur:
                # 统一用「码位整数」集合，避免与字体侧（int）比较时类型不一致
                per[cur] |= {ord(c) for c in s[1:-1]}
    return per


def font_sets():
    """{字体资产标识: 字符码位集合}"""
    out = {}
    for path, label in ((SA0, 'sharedassets0'), (RES, 'resources')):
        if not os.path.exists(path):
            continue
        f = UnityFile(path, verbose=False)
        for o in f.objects:
            if o['classID'] != 114 or o['byteSize'] < 100000:
                continue
            raw = f.buf[o['abs']:o['abs'] + o['byteSize']]
            # 必须合并「全部」游程：字符表按码位分成多段（ASCII / 假名 / 汉字 / 全角…），
            # 只取最长一段会把同字体已有的 ASCII 与标点误判成缺字。
            cs = set()
            for _, vals in PTF.detect_runs(raw, 64):
                cs |= set(vals)
            if len(cs) > 500:
                out[f'{label}:{o["byteSize"]}'] = cs
    return out


def dll_chars():
    if not os.path.exists(DLL):
        return set()
    pe = PE(DLL)
    s = set()
    for t in parse_us(pe):
        for ch in t:
            if ord(ch) > 0x7F:
                s.add(ord(ch))
    return s


def main():
    os.makedirs(OUT, exist_ok=True)
    f, tas = load_scripts()
    print(f'[1] 剧本 {len(tas)} 个')
    per_lang = dict((l, set()) for l in list(LANGS) + ['(未标注)'])
    for t in tas:
        if 'script' not in t:
            continue
        txt = t['script'].decode('utf-8', 'replace')
        for k, v in split_lang(txt).items():
            per_lang[k] |= v
    alltext = set()
    for k, v in per_lang.items():
        alltext |= v
        print(f'    语言标签 {k:<10} 用到 {len(v)} 个非 ASCII 字符')
    dll = dll_chars()
    print(f'[2] DLL 内文本 {len(dll)} 个非 ASCII 字符')

    fonts = font_sets()
    print(f'[3] 字体资产 {len(fonts)} 个:')
    for k, v in sorted(fonts.items(), key=lambda x: -len(x[1])):
        print(f'    {k:<28} {len(v)} 字形')

    union = set()
    for v in fonts.values():
        union |= v

    lines = []
    lines.append('=== 语言标签 × 字体 缺字矩阵 ===')
    keys = sorted(fonts.keys(), key=lambda k: -len(fonts[k]))
    header = '语言标签'.ljust(12) + ''.join(k.split(':')[1].rjust(10) for k in keys)
    lines.append(header)
    for lang in list(LANGS) + ['(未标注)']:
        need = per_lang[lang]
        if not need:
            continue
        row = f'{lang:<12}'
        for k in keys:
            miss = need - fonts[k]
            row += str(len(miss)).rjust(10)
        lines.append(row + f'    (需 {len(need)} 字)')

    lines.append('')
    lines.append('=== 全局：任何字体都没有的字 ===')
    gmiss = sorted(alltext - union)
    lines.append(f'共 {len(gmiss)} 个: ' + ''.join(chr(c) for c in gmiss))

    lines.append('')
    lines.append('=== 逐字体缺字（针对全部台词文本） ===')
    for k in keys:
        miss = sorted(alltext - fonts[k])
        lines.append(f'--- {k} 缺 {len(miss)} 个')
        lines.append(''.join(chr(c) for c in miss)[:600])

    report = '\n'.join(lines)
    open(os.path.join(OUT, 'cov_report.txt'), 'w', encoding='utf-8').write(report)
    for lang, v in per_lang.items():
        safe = lang.replace('(', '').replace(')', '')
        open(os.path.join(OUT, f'lang_{safe}.txt'), 'w', encoding='utf-8').write(''.join(chr(c) for c in sorted(v)))
    open(os.path.join(OUT, 'missing_all_fonts.txt'), 'w', encoding='utf-8').write(''.join(chr(c) for c in gmiss))
    print(report)
    print(f'\n报告 -> {os.path.join(OUT, "cov_report.txt")}')


if __name__ == '__main__':
    main()
