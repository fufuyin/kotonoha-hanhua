#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分块扫描大文件的日文文本（UTF-8 / UTF-16LE），统计每文件字符量与去重样例。
适用于 GB 级 .resS / .assets。
用法: python scan_bin.py <root> [--ext .assets,.resS] [--top 40] [--dump out_dir]
"""
import sys, os, re, argparse, json
from collections import Counter

JP = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF66-\uFF9F]+')
KANA = re.compile(r'[\u3040-\u309F\u30A0-\u30FF]')
CHUNK = 8 * 1024 * 1024
OVERLAP = 1024

def scan(path, dump=None):
    stats = {'utf-8': [0, 0], 'utf-16-le': [0, 0]}  # [chars, hits]
    uniq = set()
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        off = 0
        tail = {e: b'' for e in ('utf-8', 'utf-16-le')}
        while off < size:
            buf = f.read(CHUNK)
            if not buf:
                break
            for enc in ('utf-8', 'utf-16-le'):
                data = tail[enc] + buf
                if enc == 'utf-16-le' and len(data) % 2:
                    data = data[:-1]
                text = data.decode(enc, errors='ignore')
                for m in JP.finditer(text):
                    s = m.group(0)
                    if len(s) >= 2:
                        stats[enc][1] += 1
                        stats[enc][0] += len(s)
                        if dump and len(uniq) < 200000:
                            uniq.add(s)
                keep = OVERLAP if enc == 'utf-8' else OVERLAP * 2
                if enc == 'utf-16-le' and keep % 2:
                    keep += 1
                tail[enc] = data[-keep:]
            off += len(buf)
    return stats, uniq

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root')
    ap.add_argument('--ext', default='.assets,.resS,.resource,')
    ap.add_argument('--top', type=int, default=40)
    ap.add_argument('--dump', default=None)
    a = ap.parse_args()
    exts = [e.strip() for e in a.ext.split(',')]
    rows = []
    alluniq = set()
    for dp, dn, fn in os.walk(a.root):
        for f in fn:
            if f == 'scan_bin.py':
                continue
            p = os.path.join(dp, f)
            if exts and not any(f.endswith(e) for e in exts):
                continue
            try:
                st, uniq = scan(p, dump=a.dump)
            except Exception as e:
                print(f'ERR {p}: {e}', file=sys.stderr)
                continue
            chars = st['utf-8'][0] + st['utf-16-le'][0]
            if chars:
                rows.append((chars, st, p, len(uniq)))
                alluniq |= uniq
    rows.sort(key=lambda x: -x[0])
    print(f"{'chars':>10} {'u8':>9} {'u16':>9} {'uniq':>7}  file")
    for chars, st, p, nu in rows[:a.top]:
        print(f"{chars:>10} {st['utf-8'][0]:>9} {st['utf-16-le'][0]:>9} {nu:>7}  {p}")
    print(f"\nfiles_with_jp={len(rows)}  total_chars={sum(r[0] for r in rows)}  union_uniq={len(alluniq)}")
    if a.dump:
        os.makedirs(a.dump, exist_ok=True)
        outp = os.path.join(a.dump, 'bin_uniq_jp.txt')
        with open(outp, 'w', encoding='utf-8') as fh:
            for s in sorted(alluniq, key=lambda s: (-len(s), s)):
                fh.write(s + '\n')
        print('dump ->', outp)

if __name__ == '__main__':
    main()
