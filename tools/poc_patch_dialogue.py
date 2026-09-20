#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最小可行样本（PoC）：把 Story_00_00 开场台词替换为中文，原地写回 resources.assets。
原理：TextAsset 的 m_Script 是「长度前缀 + UTF-8 字节 + 4 字节对齐」。
     只要保持声明的字节长度不变（中文比日文短，尾部用换行补齐），
     整个序列化文件的对象偏移全部不变 -> 无需重建资源。

用法:
  python poc_patch_dialogue.py --dry-run     # 只报告，不写盘
  python poc_patch_dialogue.py --apply       # 写盘并回读校验
  python poc_patch_dialogue.py --restore     # 从备份还原
"""
import os, sys, argparse, shutil, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile

ASSETS = 'kotonoha_Data/resources.assets'
BACKUP = '_hanhua/backup/resources.assets.orig'
NAME = 'Story_00_00'

OLD = (
    '<main><japan><3><akane><1><right>\n'
    '<あ～～～>\n'
    '\n'
    '<main><japan><3><aoi_1><1><left>\n'
    '<お～～～>'
)
NEW = (
    '<main><japan><3><akane><1><right>\n'
    '<汉化测试：们这说汉欢众。>'
)


def find_ta(uf):
    for t in uf.textassets():
        if t.get('name') == NAME:
            return t
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--restore', action='store_true')
    a = ap.parse_args()

    if a.restore:
        shutil.copyfile(BACKUP, ASSETS)
        print(f'[restore] {ASSETS} <- {BACKUP}')
        return

    uf = UnityFile(ASSETS, verbose=False)
    t = find_ta(uf)
    if not t:
        print(f'!! TextAsset {NAME} not found'); return
    declared = t['script_len']
    script = t['script'].decode('utf-8')
    print(f'[find] {NAME} declaredLen={declared} off={t["script_off"]} objSize={t["obj"]["byteSize"]}')

    old_b, new_b = OLD.encode('utf-8'), NEW.encode('utf-8')
    if old_b not in t['script']:
        print('!! 找不到待替换片段（原文可能已改动）'); return
    replaced = t['script'].replace(old_b, new_b, 1)
    print(f'[calc] old片段={len(old_b)}B  new片段={len(new_b)}B  替换后={len(replaced)}B  声明长度={declared}B')

    if len(replaced) > declared:
        print(f'!! 中文更长，超出 {len(replaced)-declared}B；PoC 需保持等长'); return
    padded = replaced + b'\n' * (declared - len(replaced))
    print(f'[pad ] 尾部补 {declared-len(replaced)} 个换行，总长仍是 {len(padded)}B')

    if a.dry_run or not a.apply:
        print('[dry-run] 未写盘。示例前 220 字节：')
        print(padded[:220].decode('utf-8'))
        return

    # 原地写入：注意 m_Script 的长度前缀保持不变（未写入），只覆盖内容区
    with open(ASSETS, 'r+b') as f:
        f.seek(t['script_off'])
        f.write(padded)
    print('[write] 已原地写入')

    # 回读校验
    uf2 = UnityFile(ASSETS, verbose=False)
    t2 = find_ta(uf2)
    print(f'[verify] 文件大小={os.path.getsize(ASSETS)} (应 36568192)')
    print(f'[verify] 对象数={len(uf2.objects)} 全部有效={uf2._objects_valid}')
    print(f'[verify] {NAME} 长度={t2["script_len"]} (应 {declared})')
    got = t2['script'].decode('utf-8')
    print(f'[verify] 含中文片段={"汉化测试：们这说汉欢众。" in got}')
    print('--- 回读内容（前 200 字符）---')
    print(got[:200])


if __name__ == '__main__':
    main()
