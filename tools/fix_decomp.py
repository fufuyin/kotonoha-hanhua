#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 dnSpy 反编译产物中无法直接编译的语法：
  1. 编译器生成标识符中的尖括号：<>9__1 / <>4__this / <>c__DisplayClass / <PrivateImplementationDetails>
     → 统一替换为合法标识符（双下划线），且全文件一致替换（仅影响编译器生成类型，不影响 MonoBehaviour 类名）
  2. base..ctor(); —— 构造函数体内的基类构造调用（C# 非法）
用法: python fix_decomp.py <src_dir> <dst_dir> [--report]
"""
import os, re, sys, argparse, collections

SUBS = [
    (re.compile(r'<PrivateImplementationDetails>'), '__PrivateImplementationDetails__'),
    (re.compile(r'<\>f__AnonymousType(\d+)'), r'__AnonymousType\1'),
    (re.compile(r'<>c__DisplayClass'), '__c__DisplayClass'),
    (re.compile(r'<>f__'), '__f__'),
    (re.compile(r'<>l__'), '__l__'),
    (re.compile(r'<>m__'), '__m__'),
    (re.compile(r'<>(\d+)__(\w+)'), r'__\1__\2'),
    (re.compile(r'<(\w+)>j__TPar'), r'__\1__j__TPar'),
    (re.compile(r'<>(\w+)'), r'__\1'),
]


def fix_text(s, stats):
    for rx, rep in SUBS:
        s, n = rx.subn(rep, s)
        if n:
            stats[rx.pattern] += n
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--report', action='store_true')
    a = ap.parse_args()
    stats = collections.Counter()
    base_ctor_files = []
    n = 0
    for dp, dn, fn in os.walk(a.src):
        rel = os.path.relpath(dp, a.src)
        outdir = os.path.join(a.dst, rel) if rel != '.' else a.dst
        os.makedirs(outdir, exist_ok=True)
        for f in fn:
            if not f.endswith('.cs'):
                continue
            p = os.path.join(dp, f)
            src = open(p, encoding='utf-8', errors='surrogateescape').read()
            if 'base..ctor()' in src:
                base_ctor_files.append(p)
            fixed = fix_text(src, stats)
            with open(os.path.join(outdir, f), 'w', encoding='utf-8', errors='surrogateescape') as fh:
                fh.write(fixed)
            n += 1
    print(f'files processed: {n}')
    for k, v in stats.most_common():
        print(f'  {v:>7}  {k}')
    print(f'files containing base..ctor(): {len(base_ctor_files)}')
    for p in base_ctor_files[:10]:
        print('   ', os.path.basename(p))


if __name__ == '__main__':
    main()
