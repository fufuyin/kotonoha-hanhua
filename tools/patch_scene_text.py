#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
场景内未翻译日文 → 中文（原地等长改写）。

规则与 BGM 补丁一致：
  * i32 长度不可变 → 中文更短时用 U+3000 补齐到原字节长度，且差值必须被 3 整除
  * 只校验「新引入」的字符是否在渲染字体字符集内（原串已有字符不视为回归）
用法: python patch_scene_text.py [--apply]
"""
import os, sys, struct, argparse, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
import parse_tmp_font as PTF

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
DATA = os.path.join(ROOT, 'kotonoha_Data')
SA0 = os.path.join(DATA, 'sharedassets0.assets')
PAD = '\u3000'

MAP = {
    'level121': {
        'ゲーム中に表示されたＣＧを\n見ることができます': '查看游戏中出现过的\n事件插画',
        'ゲーム進行で変わる\nメニューのＣＧを見れます': '随游戏进度变化的\n菜单插画',
        'ゲーム中に流れたＢＧＭが\n聞けます': '收听游戏中播放过的\n音乐',
    },
    'level4': {
        'タイトル画面に戻ります\nセーブした部分までしかデータは残りません':
            '返回标题画面\n只会保留已保存的部分',
        'ボス以外の敵は３回勝てなかった場合、\nコマンドに逃げるが追加されます':
            '除首领外的敌人若三次未能战胜、\n指令中会追加「逃跑」',
    },
}


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


def find_string(buf, target):
    bs = target.encode('utf-8')
    i = buf.find(bs)
    return i if i >= 0 else -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    gy = gyate_charset()
    print(f'Gyate 字符集: {len(gy)} 码位')
    jobs, problems = [], []
    for fname, pairs in MAP.items():
        path = os.path.join(DATA, fname)
        buf = bytearray(open(path, 'rb').read())
        for ja, cn in pairs.items():
            off = find_string(buf, ja)
            if off < 0:
                problems.append(f'!! {fname}: 找不到原串 {ja[:20]!r}')
                continue
            L = len(ja.encode('utf-8'))
            raw = cn.encode('utf-8')
            if len(raw) > L:
                problems.append(f'!! {fname}: 中文更长 {ja[:16]!r} {L}B -> {len(raw)}B')
                continue
            diff = L - len(raw)
            if diff % 3 != 0:
                problems.append(f'!! {fname}: 补齐不整除 {ja[:16]!r} L={L} cn={len(raw)}B 差={diff}')
                continue
            newc = set(cn) - set(ja)
            miss = [c for c in newc if ord(c) not in gy]
            if miss:
                problems.append(f'!! {fname}: 新字符缺字形 {ja[:16]!r} -> {cn[:16]!r} 缺 {miss}')
                continue
            jobs.append((fname, off, L, ja, cn + PAD * (diff // 3)))
    print(f'可安全替换: {len(jobs)} 条')
    if problems:
        print('--- 问题 ---')
        for p in problems:
            print('   ' + p)
    for fname, off, L, ja, rep in jobs:
        print(f'   [{fname} @{off}] {ja[:24]!r} -> {rep[:24]!r} ({len(rep.encode("utf-8"))}B/{L}B)')
    if not a.apply:
        print('\n[dry-run] 未写盘'); return
    if problems:
        print('\n!! 存在问题，拒绝写盘'); return
    for fname in set(f for f, *_ in jobs):
        path = os.path.join(DATA, fname)
        bk = os.path.join(ROOT, '_hanhua', 'backup', fname + '.before_text')
        if not os.path.exists(bk):
            shutil.copyfile(path, bk)
        buf = bytearray(open(path, 'rb').read())
        n = 0
        for f2, off, L, ja, rep in jobs:
            if f2 != fname:
                continue
            buf[off:off + L] = rep.encode('utf-8')
            n += 1
        open(path, 'wb').write(bytes(buf))
        print(f'[write] {fname}: {n} 条 (备份 {os.path.basename(bk)})')
    # 回读校验
    for fname in set(f for f, *_ in jobs):
        path = os.path.join(DATA, fname)
        buf = open(path, 'rb').read()
        left = sum(1 for ja in MAP[fname] if ja.encode('utf-8') in buf)
        uf = UnityFile(path, verbose=False)
        print(f'[verify] {fname}: 残留日文串={left}  对象数={len(uf.objects)} 全部有效={uf._objects_valid} 大小={len(buf)}')


if __name__ == '__main__':
    main()
