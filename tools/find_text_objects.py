#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
按内容定位 TMP_Text 对象，并识别它引用的材质（不需要完整字段解析器）。

做法：扫 .assets 里 class 114 的对象，payload 含目标 UTF-8 字符串即命中；
再在 payload 里搜候选材质 pathID 的 8 字节模式（前面 4 字节 = fileID）→ 得到材质归属。

用法: python find_text_objects.py <dir> <字符串> [字符串...] [--mats 0x1a,0x1b,...]
"""
import os, struct, sys, argparse, glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from unityfile import UnityFile
from splice_fonts import obj_payload

DEFAULT_MATS = ['0x1a', '0x1b', '0x1c', '0x1d', '0x78', '0x2', '0x3', '0x4', '0x5', '0x6', '0x9', '0xd']


def scan_file(path, needles, mat_ids):
    try:
        f = UnityFile(path, verbose=False)
    except Exception as e:
        return [f'  !! {os.path.basename(path)} 解析失败: {e}']
    out = []
    for o in f.objects:
        if o['classID'] != 114:
            continue
        p = obj_payload(f, o)
        for s in needles:
            b = s.encode('utf-8')
            if b not in p:
                continue
            # 字符串上下文（Unity 字符串：i32 长度 + 内容）
            ctx = []
            i = p.find(b)
            n = struct.unpack_from('<i', p, i - 4)[0] if i >= 4 else -1
            # 材质归属
            mats = []
            for mid in mat_ids:
                pat = struct.pack('<Q', mid)
                j = 0
                while True:
                    j = p.find(pat, j)
                    if j < 0:
                        break
                    fid = struct.unpack_from('<i', p, j - 4)[0] if j >= 4 else None
                    mats.append((hex(mid), fid))
                    j += 1
            out.append(f'  [{os.path.basename(path)}] pathID=0x{o["pathID"] & 0xFFFFFFFFFFFFFFFF:x} '
                       f'size={o["byteSize"]} str={s!r}(len字段={n}) 材质PPtr={mats[:6]}')
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dir')
    ap.add_argument('strings', nargs='+')
    ap.add_argument('--mats', default=','.join(DEFAULT_MATS))
    a = ap.parse_args()
    mats = [int(x, 16) for x in a.mats.split(',') if x.strip()]
    files = []
    for pat in ('*.assets', 'level*', 'resources.assets*'):
        files += glob.glob(os.path.join(a.dir, pat))
    files = [f for f in files if not f.endswith('.resS')]
    print(f'扫描 {len(files)} 个文件，目标串 {a.strings}')
    for path in sorted(set(files)):
        rows = scan_file(path, a.strings, mats)
        if rows:
            print(f'--- {os.path.basename(path)}')
            for r in rows:
                print(r)


if __name__ == '__main__':
    main()
