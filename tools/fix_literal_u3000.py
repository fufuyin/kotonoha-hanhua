#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复前作者翻译里的「字面 u3000」缺陷。

现象：道具/成就等简介里显示 "u3000勤勤恳恳地..." —— 前作者把转义 \u3000 写成了字面 5 个 ASCII 字符。
修法：把 5 字节的 "u3000" 换成 3 字节的真正 U+3000 全角空格；每个替换少 2 字节，
      在**该字符串末尾**补同等数量的换行（纯排版字符，不占字形），使声明长度与后续字段保持不变。
用法: python fix_literal_u3000.py [--apply]
"""
import os, sys, struct, argparse, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
RES = os.path.join(ROOT, 'kotonoha_Data', 'resources.assets')
BACKUP = os.path.join(ROOT, '_hanhua', 'backup', 'resources.assets.before_u3000')
BAD = 'u3000'
GOOD = '\u3000'


def unity_strings(raw, lo=1, hi=4000):
    out = []
    i = 0
    n = len(raw)
    while i + 4 <= n:
        L = struct.unpack_from('<i', raw, i)[0]
        if lo <= L <= hi and i + 4 + L <= n:
            bs = raw[i + 4:i + 4 + L]
            if b'\x00' not in bs:
                try:
                    s = bs.decode('utf-8')
                except UnicodeDecodeError:
                    i += 1
                    continue
                out.append((i + 4, L, s))
                i += 4 + L
                i = (i + 3) & ~3
                continue
        i += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    uf = UnityFile(RES, verbose=False)
    buf = bytearray(open(RES, 'rb').read())
    plans = []
    nstr = 0
    nocc = 0
    for o in uf.objects:
        if o['classID'] == 114 and o['byteSize'] > 100000:
            continue
        raw = uf.buf[o['abs']:o['abs'] + o['byteSize']]
        if BAD.encode() not in raw:
            continue
        for off, L, s in unity_strings(raw):
            if BAD not in s:
                continue
            cnt = s.count(BAD)
            new = s.replace(BAD, GOOD)
            pad = (len(s.encode('utf-8')) - len(new.encode('utf-8')))  # = 2*cnt
            new = new + '\n' * pad
            if len(new.encode('utf-8')) != L:
                print(f'!! 长度不匹配 @{o["abs"]+off}: {L} -> {len(new.encode("utf-8"))}')
                continue
            plans.append((o['abs'] + off, L, s, new))
            nstr += 1
            nocc += cnt
    print(f'受影响字符串: {nstr} 个，字面 u3000 共 {nocc} 处')
    for off, L, s, new in plans[:5]:
        print(f'   @{off} L={L}')
        print(f'      原: {s[:60]!r}')
        print(f'      新: {new[:60]!r}')
    if not a.apply:
        print('\n[dry-run] 未写盘'); return
    if not os.path.exists(BACKUP):
        shutil.copyfile(RES, BACKUP)
        print(f'备份 -> {BACKUP}')
    for off, L, s, new in plans:
        buf[off:off + L] = new.encode('utf-8')
    open(RES, 'wb').write(bytes(buf))
    print(f'[write] 已修复 {len(plans)} 个字符串')
    f2 = UnityFile(RES, verbose=False)
    left = 0
    for o in f2.objects:
        if o['classID'] == 114 and o['byteSize'] > 100000:
            continue
        raw = f2.buf[o['abs']:o['abs'] + o['byteSize']]
        left += raw.count(BAD.encode())
    print(f'[verify] 对象数={len(f2.objects)} 全部有效={f2._objects_valid} 大小={os.path.getsize(RES)}')
    print(f'[verify] 残留字面 u3000: {left}')


if __name__ == '__main__':
    main()
