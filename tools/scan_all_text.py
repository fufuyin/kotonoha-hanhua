#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全资源文本清点：遍历所有 .assets 文件的所有对象，提取对象数据中的日文串，
按 文件/类/对象 归属统计。用于确认 TextAsset 之外是否还有文本来源
（如 MonoBehaviour 字符串字段、Texture 名称等）。

注意：对二进制块 decode 会产生假阳性，故要求连续日文串 >= MINRUN，并输出样本供人工核对。

用法: python scan_all_text.py <root> [--minrun 4] [--csv out.csv] [--samples 40]
"""
import os, sys, argparse, re, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile, CLASS_NAMES

JP_RUN = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF66-\uFF9F]{4,}')
KANA = re.compile(r'[\u3040-\u309F\u30A0-\u30FF]')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root')
    ap.add_argument('--minrun', type=int, default=4)
    ap.add_argument('--csv', default=None)
    ap.add_argument('--samples', type=int, default=40)
    a = ap.parse_args()
    jp_run = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF66-\uFF9F]{%d,}' % a.minrun)
    rows = []
    samples = []
    files = []
    for dp, dn, fn in os.walk(a.root):
        for f in fn:
            if f.endswith('.assets') or f.startswith('level') and '.' not in f:
                files.append(os.path.join(dp, f))
    files.sort()
    for p in files:
        try:
            uf = UnityFile(p, verbose=False)
        except Exception as e:
            print(f'ERR {p}: {e}', file=sys.stderr)
            continue
        from collections import Counter
        per_class = Counter()
        ta_count = 0
        for o in uf.objects:
            if o['classID'] == 49:
                ta_count += 1
            raw = uf.buf[o['abs']:o['abs']+o['byteSize']]
            if not raw:
                continue
            t = raw.decode('utf-8', 'ignore')
            hits = jp_run.findall(t)
            if not hits:
                continue
            kana_hits = [h for h in hits if KANA.search(h)]
            if len(kana_hits) < 2:
                continue   # 无假名 → 大概率是二进制假阳性
            n = sum(len(h) for h in kana_hits)
            per_class[o['classID']] += n
            if len(samples) < a.samples * 8:
                for h in kana_hits[:2]:
                    samples.append((p, o['classID'], CLASS_NAMES.get(o['classID'], '?'), h[:60]))
        tot = sum(per_class.values())
        if tot:
            detail = ', '.join(f'{CLASS_NAMES.get(c,"?")}({c}):{n}' for c, n in per_class.most_common())
            print(f'{tot:>8} chars  TextAssets={ta_count:<4} {p}  [{detail}]')
            rows.append((p, tot, ta_count, detail))
    print('\n=== 样本（请人工核对是否为真实文本）===')
    seen = set()
    cnt = 0
    for p, cid, cn, txt in samples:
        key = (cn, txt[:20])
        if key in seen:
            continue
        seen.add(key)
        print(f'  [{cn:<14}] {txt!r}')
        cnt += 1
        if cnt >= a.samples:
            break
    if a.csv:
        with open(a.csv, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['file', 'jp_chars_with_kana', 'textasset_count', 'by_class'])
            w.writerows(rows)
        print('csv ->', a.csv)


if __name__ == '__main__':
    main()
