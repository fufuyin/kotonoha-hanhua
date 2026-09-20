#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 TMP_FontAsset（MonoBehaviour, class 114）提取已烘焙字符集，并可核对译文缺字。

记录布局（实测）: 每 16 字节 = [unicode u32][glyphIndex u32][scale f32][u32]，按 unicode 升序。
探测：按 16 字节对齐向上增长，要求相邻 unicode 严格递增且跳幅受限。

用法:
  python parse_tmp_font.py <assets_file> [--dump charset.txt]
  python parse_tmp_font.py <assets_file> --check-text <dir_or_csv>   # 核对缺字
"""
import sys, os, struct, argparse, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile

REC = 16
MAX_JUMP = 0x4000


def _u32(raw, off):
    return struct.unpack_from('<I', raw, off)[0]


def _is_unicode(v):
    return 0x20 <= v <= 0x10FFFF and not (0xD800 <= v <= 0xDFFF)


def detect_runs(raw, min_run=64):
    n = len(raw)
    runs = []
    j = 0
    while j <= n - REC * 2:
        v, w = _u32(raw, j), _u32(raw, j + REC)
        if _is_unicode(v) and v < w <= v + MAX_JUMP:
            k = j
            cnt = 1
            while k + REC * 2 <= n:
                a, b = _u32(raw, k), _u32(raw, k + REC)
                if _is_unicode(a) and a < b <= a + MAX_JUMP:
                    k += REC
                    cnt += 1
                else:
                    break
            if cnt >= min_run:
                runs.append((j, [_u32(raw, j + i * REC) for i in range(cnt + 1)]))
            j = k + REC
        else:
            j += 4
    return runs


def font_charsets(path, min_run=64, verbose=True):
    f = UnityFile(path, verbose=False)
    total = set()
    info = []
    for o in f.objects:
        if o['classID'] != 114:
            continue
        raw = f.buf[o['abs']:o['abs'] + o['byteSize']]
        for start, vals in detect_runs(raw, min_run):
            cs = set(vals)
            total |= cs
            info.append((o['byteSize'], o['abs'], start, len(vals), cs))
    if verbose:
        for size, abs_, start, cnt, cs in sorted(info, key=lambda x: -x[3]):
            kana = sum(1 for v in cs if 0x3040 <= v <= 0x30FF)
            han = sum(1 for v in cs if 0x4E00 <= v <= 0x9FFF)
            asc = sum(1 for v in cs if 0x20 <= v <= 0x7E)
            print(f'   objSize={size:>8} abs={abs_:>10} 表偏移={start:>7} 条目={cnt:>6} ascii={asc} 假名={kana} 汉字={han}')
        print(f'   => 已烘焙字符并集: {len(total)} 码位')
    return total


def collect_text_chars(paths):
    chars = set()
    for p in paths:
        try:
            data = open(p, 'rb').read()
        except Exception:
            continue
        for enc in ('utf-8',):
            try:
                s = data.decode(enc, errors='ignore')
            except Exception:
                continue
            for ch in s:
                o = ord(ch)
                if o >= 0x80 or 0x20 <= o <= 0x7E:
                    chars.add(o)
    return chars


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--dump', default=None)
    ap.add_argument('--check-dir', default=None, help='要核对缺字的文本目录（.txt）')
    ap.add_argument('--min-run', type=int, default=64)
    a = ap.parse_args()
    print(f'[{a.path}]')
    cs = font_charsets(a.path, a.min_run)
    if a.dump:
        with open(a.dump, 'w', encoding='utf-8') as fh:
            fh.write(''.join(chr(v) for v in sorted(cs)))
        print('   dump ->', a.dump)
    if a.check_dir:
        files = glob.glob(os.path.join(a.check_dir, '*.txt'))
        tc = collect_text_chars(files)
        # 只关心需要字形渲染的字符（排除 ASCII 控制与常见空白）
        need = {c for c in tc if c > 0x7F or (0x21 <= c <= 0x7E)}
        missing = sorted(need - cs)
        print(f'   译文/文本用到 {len(need)} 个字符；字体已烘焙 {len(cs & need)} 个')
        print(f'   >>> 缺字 {len(missing)} 个')
        if missing:
            print('   缺字示例:', ''.join(chr(c) for c in missing[:120]))
            with open(os.path.join(os.path.dirname(a.dump or '.'), 'missing_chars.txt'), 'w', encoding='utf-8') as fh:
                fh.write(''.join(chr(c) for c in missing))
            print('   缺字清单 -> missing_chars.txt')


if __name__ == '__main__':
    main()
