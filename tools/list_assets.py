#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
列出 Unity 资源文件中所有对象的类与名称（用于清点字体/贴图/音频等资产）。
多数 Unity 类的首个序列化字段是 m_Name；MonoBehaviour 不含名称（会标 ?）。

用法:
  python list_assets.py <file> [--filter SDF] [--class 128] [--names-only] [--csv out.csv]
"""
import sys, os, argparse, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile, R, CLASS_NAMES

# 首字段即 m_Name 的常见类（其余类名可能读错位，加 ? 标记）
NAMED_CLASSES = {1, 4, 21, 28, 33, 43, 48, 49, 74, 83, 89, 128, 142, 213, 222, 223, 224,
                 225, 258, 150, 152, 156, 198, 199, 1001, 1002, 1003, 1004, 1005, 115, 114}


def read_name(f, o):
    """尝试读出对象名；MonoBehaviour 需跳过头部字段，此处只对已知类尝试首字段。"""
    r = R(f.buf, o['abs'])
    if o['classID'] == 114:
        # MonoBehaviour: m_GameObject(PPtr 12) + m_Enabled(1) ... 非脚本资产常无 GameObject
        # 不做猜测，返回 None
        return None
    try:
        s = r.ustr()
        if len(s) > 200:
            return None
        return s.decode('utf-8', 'replace')
    except Exception:
        return None


def ascii_strings(buf, minlen=4):
    return set(m.group(0).decode('ascii') for m in re.finditer(rb'[\x20-\x7e]{%d,}' % minlen, buf))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--filter', default=None, help='名称包含该子串（忽略大小写）')
    ap.add_argument('--class', dest='cls', type=int, default=None)
    ap.add_argument('--csv', default=None)
    a = ap.parse_args()
    f = UnityFile(a.path, verbose=False)
    from collections import Counter
    cnt = Counter()
    rows = []
    for o in f.objects:
        cn = CLASS_NAMES.get(o['classID'], '?')
        cnt[(o['classID'], cn)] += 1
        if a.cls is not None and o['classID'] != a.cls:
            continue
        nm = read_name(f, o)
        if nm is None:
            continue
        if a.filter and a.filter.lower() not in nm.lower():
            continue
        rows.append((o['classID'], cn, nm, o['byteSize'], o['abs']))
    print(f'== {a.path}: {len(f.objects)} objects, {len(f.types)} types ==')
    for (cid, cn), c in cnt.most_common(25):
        print(f'  classID={cid:>4} {cn:<16} {c}')
    print(f'== matched named objects: {len(rows)} ==')
    for cid, cn, nm, sz, off in rows[:200]:
        print(f'  [{cid:>4}] {cn:<14} {nm!r} size={sz} off={off}')
    if a.csv:
        import csv
        with open(a.csv, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['classID', 'class', 'name', 'byteSize', 'offset'])
            w.writerows(rows)
        print('csv ->', a.csv)


if __name__ == '__main__':
    main()
