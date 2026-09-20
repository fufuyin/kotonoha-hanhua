#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对话高频缺字替换（纯字节 1:1，长度与文件大小完全不变）。

背景：主中文字体 Gyate（212484 那支）的字符表只覆盖 U+3000..U+FF01 的稀疏子集，
      缺 ～(U+FF5E)、・(U+30FB)、…(U+2026)、—(U+2014) 等；而 、(U+3001) 。(U+3002) 〜(U+301C) 有字形。
      这些字符在 UTF-8 下都是 3 字节，因此可以做等长字节替换 —— 不改变任何长度、无偏移风险。

规则：
  * 连续 2 个及以上的 ・ 或 …  -> 同数量的 。
  * 单个 ・                    -> 、
  * ～                        -> 〜
  * —                         -> 〜
用法: python patch_dialogue_punct.py [--apply]
"""
import os, sys, argparse, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
import parse_tmp_font as PTF

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
RES = os.path.join(ROOT, 'kotonoha_Data', 'resources.assets')
SA0 = os.path.join(ROOT, 'kotonoha_Data', 'sharedassets0.assets')
BACKUP = os.path.join(ROOT, '_hanhua', 'backup', 'resources.assets.before_punct')

PAIRS = {'～': '。', '—': '。', '，': '、'}


def gyate_charset():
    f = UnityFile(SA0, verbose=False)
    for o in f.objects:
        if o['classID'] == 114 and o['byteSize'] == 212484:
            raw = f.buf[o['abs']:o['abs'] + o['byteSize']]
            cs = set()
            for _, vals in PTF.detect_runs(raw, 64):
                cs |= set(vals)
            return cs
    return set()


def transform(s):
    """按规则替换；返回新串"""
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c in ('・', '…'):
            j = i
            while j < n and s[j] in ('・', '…'):
                j += 1
            k = j - i
            out.append('。' * k if k >= 2 else '、')
            i = j
            continue
        out.append(PAIRS.get(c, c))
        i += 1
    return ''.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    gy = gyate_charset()
    print(f'Gyate 字符集: {len(gy)} 码位')
    bad = [c for c in set(PAIRS.values()) if ord(c) not in gy]
    print(f'替换目标可用性: 目标={sorted(set(PAIRS.values()))} 缺字形={bad}')
    if bad:
        print('!! 替换目标不在字体集内，终止'); return

    uf = UnityFile(RES, verbose=False)
    tas = [t for t in uf.textassets() if 'script' in t]
    print(f'剧本数: {len(tas)}')

    buf = bytearray(open(RES, 'rb').read())
    total_changed = 0
    stat = {}
    plans = []
    for t in tas:
        s = t['script'].decode('utf-8')
        ns = transform(s)
        if ns == s:
            continue
        b_old, b_new = s.encode('utf-8'), ns.encode('utf-8')
        if len(b_old) != len(b_new):
            print(f'!! 长度变化 {t["name"]}: {len(b_old)} -> {len(b_new)}'); return
        plans.append((t, b_new))
        for k, v in PAIRS.items():
            c = s.count(k)
            if c:
                stat[k] = stat.get(k, 0) + c
        total_changed += 1
    print(f'需要改写的剧本: {total_changed} 个')
    print(f'替换统计: ' + ', '.join(f'{k}×{v}' for k, v in sorted(stat.items(), key=lambda x: -x[1])))
    print('--- 预览 3 例 ---')
    for t, b_new in plans[:3]:
        print(f'   {t["name"]}: {b_new.decode("utf-8")[:110]!r}')

    if not a.apply:
        print('\n[dry-run] 未写盘'); return
    if not os.path.exists(BACKUP):
        shutil.copyfile(RES, BACKUP)
        print(f'备份 -> {BACKUP}')
    for t, b_new in plans:
        buf[t['script_off']:t['script_off'] + t['script_len']] = b_new
    open(RES, 'wb').write(bytes(buf))
    print(f'[write] 已改写 {len(plans)} 个剧本')

    f2 = UnityFile(RES, verbose=False)
    left = 0
    for t in f2.textassets():
        if 'script' not in t:
            continue
        s = t['script'].decode('utf-8')
        left += sum(s.count(k) for k in PAIRS)
    print(f'[verify] 对象数={len(f2.objects)} 全部有效={f2._objects_valid} 大小={os.path.getsize(RES)}')
    print(f'[verify] 残留待替换字符: {left}')


if __name__ == '__main__':
    main()
