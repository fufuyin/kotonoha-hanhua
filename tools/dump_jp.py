#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 .NET 程序集按编码提取日文字符串并去重、排序输出。
用法: python dump_jp.py <file> [--enc utf-16-le|utf-8] [--out out.txt] [--sample N]
"""
import sys, os, re, argparse

JP_RE = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF66-\uFF9F\u3000-\u303F]+')

def extract(path, enc):
    raw = open(path, 'rb').read()
    if enc == 'utf-16-le' and len(raw) % 2:
        raw = raw[:-1]
    text = raw.decode(enc, errors='ignore')
    out = []
    for m in JP_RE.finditer(text):
        s = m.group(0)
        if len(s) >= 2:
            out.append(s)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--enc', default='utf-16-le', choices=['utf-16-le', 'utf-8'])
    ap.add_argument('--out', default=None)
    ap.add_argument('--sample', type=int, default=0)
    a = ap.parse_args()
    res = extract(a.path, a.enc)
    uniq = sorted(set(res), key=lambda s: (-len(s), s))
    print(f'raw hits={len(res)} unique={len(uniq)} chars={sum(len(s) for s in uniq)} enc={a.enc}')
    if a.sample:
        for s in uniq[:a.sample]:
            print(repr(s))
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, 'w', encoding='utf-8') as f:
            for s in uniq:
                f.write(s + '\n')
        print('written ->', a.out)

if __name__ == '__main__':
    main()
