#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图库 BGM 曲名汉化（原地等长改写）。

约束：
  * 字符串序列化 = [i32 长度][UTF-8][补齐4]，长度变化会移动后续字段 → 只能等长
  * 中文比日文短，用 U+3000（全角空格）补齐到原字节长度
  * 每个替换字符必须落在实际渲染字体的字符集内（默认按 Gyate = 212484 那支校验）
用法:
  python patch_bgm_names.py --dry-run
  python patch_bgm_names.py --apply
"""
import os, sys, struct, argparse, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
import parse_tmp_font as PTF

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
RES = os.path.join(ROOT, 'kotonoha_Data', 'resources.assets')
SA0 = os.path.join(ROOT, 'kotonoha_Data', 'sharedassets0.assets')
BACKUP = os.path.join(ROOT, '_hanhua', 'backup', 'resources.assets.before_bgm')
PAD = '\u3000'

# 日文原名 -> 中文（长度必须 <= 原字节长度；中文按 UTF-8 计 3 字节/字）
MAP = {
    'メニュー画面': '菜单画面',
    '雨の日': '雨天',
    'デヒノ村': '德希诺村',
    '古のデヒノ村': '古德希诺村',
    '南の島のホテル': '南岛旅馆',
    'チーリン村': '奇林村',
    '太陽の祭壇': '太阳祭坛',
    '岩山を越えて': '越过岩山',
    'ウコゴ村': '乌科戈村',
    '雨のビーチ': '雨之海滩',
    '晴れのビーチ': '晴之海滩',
    '雨降るクレイユ街': '雨中克雷尤街',
    'クレイユ街': '克雷尤街',
    'レビーヘイン本部': '雷维海因本部',
    '秘密の地下': '秘密地下',
    '夜明け': '天亮',
    'ボーニッチ火山': '博尼奇火山',
    '雨の火山': '雨之火山',
    '王宮の地下通路': '王宫地下通道',
    '最後の遺跡': '最后遗迹',
    '南の島の戦い': '南岛之战',
    '対カブリート': '对战卡布里特',
    '対レビーヘイン': '对战雷维海因',
    '対フォライド': '对战福莱德',
    '対スコール': '对战斯考尔',
    'ED「島を巡ろう」': 'ED「环岛」',
}


def gyate_charset():
    """实际渲染字体（212484 那支）的字符集：合并全部游程"""
    if not os.path.exists(SA0):
        return set()
    f = UnityFile(SA0, verbose=False)
    for o in f.objects:
        if o['classID'] == 114 and o['byteSize'] == 212484:
            raw = f.buf[o['abs']:o['abs'] + o['byteSize']]
            cs = set()
            for _, vals in PTF.detect_runs(raw, 64):
                cs |= set(vals)
            return cs
    return set()


def find_strings(buf):
    """在 BGM 数组区域里找出所有假名串：(偏移, 声明长度, 文本)"""
    out = []
    lo, hi = 38373000, 38380000
    i = lo
    while i < hi:
        L = struct.unpack_from('<i', buf, i)[0]
        if 2 <= L <= 200 and i + 4 + L <= len(buf):
            bs = buf[i + 4:i + 4 + L]
            if b'\x00' not in bs:
                try:
                    s = bs.decode('utf-8')
                except UnicodeDecodeError:
                    i += 1
                    continue
                if any('\u3040' <= c <= '\u30ff' for c in s):
                    out.append((i + 4, L, s))
                i += 4 + L
                i = (i + 3) & ~3
                continue
        i += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    buf = bytearray(open(RES, 'rb').read())
    gy = gyate_charset()
    print(f'Gyate 字符集: {len(gy)} 码位')

    found = find_strings(buf)
    print(f'区域内找到含假名的串: {len(found)} 条')
    todo, problems = [], []
    for off, L, s in found:
        if s not in MAP:
            problems.append(f'!! 未在映射表中: {s!r} @{off}')
            continue
        cn = MAP[s]
        raw = cn.encode('utf-8')
        if len(raw) > L:
            problems.append(f'!! 中文比原文长: {s!r}({L}B) -> {cn!r}({len(raw)}B)')
            continue
        pad = (L - len(raw)) // 3
        if (L - len(raw)) % 3 != 0:
            problems.append(f'!! 补齐后长度不整除3: {s!r} L={L} cn={len(raw)}B')
        full = cn + PAD * pad
        # 只校验「新引入」的字符：原串里本就存在、且字体本来就不支持的字符（如 'ED' 里的 ASCII）
        # 不是我引入的回归，保留原样即可。
        new_chars = set(cn) - set(s)
        missing = [c for c in new_chars if ord(c) not in gy]
        if missing:
            problems.append(f'!! 字符不在字体集内: {s!r} -> {cn!r} 缺 {missing}')
            continue
        todo.append((off, L, s, cn + PAD * pad))

    print(f'可安全替换: {len(todo)} 条')
    if problems:
        print('--- 问题 ---')
        for p in problems:
            print('   ' + p)
    print('--- 预览 ---')
    for off, L, s, rep in todo[:30]:
        print(f'   @{off} L={L}  {s!r}  ->  {rep!r} ({len(rep.encode("utf-8"))}B)')

    if not a.apply:
        print('\n[dry-run] 未写盘')
        return
    if problems:
        print('\n!! 存在问题，拒绝写盘'); return
    if not os.path.exists(BACKUP):
        shutil.copyfile(RES, BACKUP)
        print(f'备份 -> {BACKUP}')
    for off, L, s, rep in todo:
        buf[off:off + L] = rep.encode('utf-8')
    open(RES, 'wb').write(bytes(buf))
    print(f'[write] 已写入 {len(todo)} 条')

    # 回读校验
    f2 = UnityFile(RES, verbose=False)
    print(f'[verify] 对象数={len(f2.objects)} 全部有效={f2._objects_valid} 文件大小={os.path.getsize(RES)}')
    again = find_strings(bytearray(open(RES, 'rb').read()))
    kana = [s for _, _, s in again if any('\u3040' <= c <= '\u30ff' for c in s)]
    print(f'[verify] 区域内剩余假名串: {len(kana)} 条 {kana[:6]}')


if __name__ == '__main__':
    main()
