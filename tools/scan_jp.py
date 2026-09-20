#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描文件中的日文字符串（UTF-8 与 UTF-16LE 两种编码），统计字符量。
用法: python scan_jp.py <path...>
"""
import sys, os, re, json
from collections import Counter

JP_RE = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF66-\uFF9F]+')
# 需要至少包含假名，才算"日文句子"（纯汉字的可能是共用字形）
KANA_RE = re.compile(r'[\u3040-\u309F\u30A0-\u30FF]')

def collect_strings(data, enc):
    if enc == 'utf-8':
        try:
            return data.decode('utf-8', errors='ignore')
        except Exception:
            return ''
    else:  # utf-16le
        if len(data) % 2:
            data = data[:-1]
        try:
            return data.decode('utf-16-le', errors='ignore')
        except Exception:
            return ''

def scan_file(path, minlen=2):
    with open(path, 'rb') as f:
        data = f.read()
    results = []
    for enc in ('utf-8', 'utf-16-le'):
        text = collect_strings(data, enc)
        for m in JP_RE.finditer(text):
            s = m.group(0)
            if len(s) >= minlen:
                results.append((enc, s))
    return results

def main():
    total_chars = 0
    total_unique = set()
    per_file = {}
    for root in sys.argv[1:]:
        if os.path.isfile(root):
            files = [root]
        else:
            files = []
            for dp, dn, fn in os.walk(root):
                for f in fn:
                    files.append(os.path.join(dp, f))
        for path in files:
            try:
                res = scan_file(path)
            except Exception as e:
                print(f'ERR {path}: {e}', file=sys.stderr)
                continue
            if not res:
                continue
            chars = sum(len(s) for _, s in res)
            uniq = set(s for _, s in res)
            kana_hits = [s for _, s in res if KANA_RE.search(s)]
            kana_chars = sum(len(s) for s in kana_hits)
            per_file[path] = {
                'hits': len(res),
                'chars': chars,
                'unique': len(uniq),
                'kana_hits': len(kana_hits),
                'kana_chars': kana_chars,
            }
            total_chars += chars
            total_unique |= uniq
    print('== per file (top 60 by chars) ==')
    for p, v in sorted(per_file.items(), key=lambda x: -x[1]['chars'])[:60]:
        print(f"{v['chars']:>9} chars  {v['hits']:>7} hits  {v['unique']:>7} uniq  kana={v['kana_chars']:>8}  {p}")
    print()
    print(f'TOTAL files with JP: {len(per_file)}')
    print(f'TOTAL chars (with overlap): {total_chars}')
    print(f'TOTAL unique strings: {len(total_unique)}')
    print(f'TOTAL unique chars: {sum(len(s) for s in total_unique)}')

if __name__ == '__main__':
    main()
