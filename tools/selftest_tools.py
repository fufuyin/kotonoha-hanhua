#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
工具链自检：把所有探针/解析器在当前真实文件上跑一遍并给 PASS/FAIL。

用途：以后跑大流水线（rebake_pipeline.ps1 等）之前先跑本脚本，
      避免自己刚写的小工具因签名/转义/布局假设错误而在流水线深处才炸。

用法: python selftest_tools.py [--game <sharedassets0.assets>] [--ref <patch_backup.assets>] [--our <serialized>]
"""
import os, sys, argparse, hashlib, struct

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from unityfile import UnityFile
from splice_fonts import find_pixels, find_pptr, parse_head, obj_payload
from splice_more import find_prop_float
from parse_tmp_font import detect_runs
from probe_faceinfo import find_faceinfo
from probe_mat_props import scan_props, read_ustr

PIX = 8192 * 8192
RESULTS = []


def check(name, fn):
    try:
        msg = fn()
        RESULTS.append((True, name, msg or 'ok'))
    except Exception as e:
        RESULTS.append((False, name, f'{type(e).__name__}: {e}'))


def main():
    ap = argparse.ArgumentParser()
    root = os.path.dirname(os.path.dirname(HERE))          # ...\kotonoha
    ap.add_argument('--game', default=os.path.join(root, 'kotonoha_Data', 'sharedassets0.assets'))
    ap.add_argument('--ref', default=os.path.join(HERE, '..', 'backup',
                                                  'sharedassets0.before_assetfix_20260912_105243.assets'))
    ap.add_argument('--our', default=os.path.join(HERE, '..', 'work', 'our_simhei.serialized'))
    ap.add_argument('--golden', default=r'F:\Application\Unity\twobake_atlas.bin')
    ap.add_argument('--charset', default=r'F:\Application\Unity\charset.txt')
    a = ap.parse_args()

    G = UnityFile(a.game, verbose=False)
    print(f'game = {a.game}\n objects={len(G.objects)} dataOffset={G.data_offset}')

    def get(pid):
        o = [x for x in G.objects if (x['pathID'] & 0xFFFFFFFFFFFFFFFF) == pid]
        assert len(o) == 1, f'找不到唯一对象 {hex(pid)}'
        return o[0], obj_payload(G, o[0])

    # 1. 字体头解析
    def t_font_head():
        o, p = get(0xbe)
        name, end, script = parse_head(p)
        assert name and len(name) > 3, name
        return f'name={name!r} name_end={end} size={o["byteSize"]}'
    check('parse_head(0xbe)', t_font_head)

    # 2. FaceInfo 签名（之前因多要求 unitsPerEM 而失效）
    def t_faceinfo():
        o, p = get(0xbe)
        fis = find_faceinfo(p)
        assert fis, 'FaceInfo 未找到（检查签名）'
        i = fis[0]
        ps = struct.unpack_from('<i', p, i)[0]
        lh = struct.unpack_from('<f', p, i + 8)[0]
        assert abs(lh / ps - 1.0) < 0.05, f'lineHeight/pointSize={lh/ps:.4f} 不是 1.0'
        return f'@+{i} pointSize={ps} lineHeight={lh:g} ratio={lh/ps:.4f}'
    check('find_faceinfo(0xbe) ratio=1.0', t_faceinfo)

    # 3. 材质属性定位
    def t_mat_prop():
        o, p = get(0x1a)
        off = find_prop_float(p, '_OutlineWidth')
        assert off is not None, '_OutlineWidth 未找到'
        v = struct.unpack_from('<f', p, off)[0]
        fl, co = scan_props(p)
        assert '_FaceColor' in co, '_FaceColor 未解析到'
        return f'_OutlineWidth={v:g} floats={len(fl)} colors={len(co)}'
    check('find_prop_float/scan_props(0x1a)', t_mat_prop)

    # 4. 图集锚点 + 黄金像素
    def t_atlas():
        o, p = get(0x53)
        po, tail = find_pixels(p)
        assert po is not None, '锚点未找到'
        px = p[po:po + PIX]
        assert len(px) == PIX
        if os.path.exists(a.golden) and os.path.getsize(a.golden) == PIX:
            g = open(a.golden, 'rb').read()
            assert g == px, '与 twobake_atlas.bin 不一致'
            return f'anchor={po} tail={tail} == golden sha={hashlib.sha256(px).hexdigest()[:16]}'
        return f'anchor={po} tail={tail} (无 golden 可比)'
    check('find_pixels(0x53)', t_atlas)

    # 5. 字符表探测
    def t_chars():
        o, p = get(0xbe)
        runs = detect_runs(p, 64)
        best = max((len(v) for _, v in runs), default=0)
        total = sum(len(v) for _, v in runs)
        assert best > 5000, f'最大段 {best} 偏小'
        return f'最大段={best} 合计={total}'
    check('detect_runs(0xbe)', t_chars)

    # 6. 覆盖率脚本能跑（之前 docstring 里 \U 转义导致语法错误）
    def t_coverage():
        want = set()
        with open(a.charset, encoding='utf-8') as fh:
            for ch in fh.read():
                if ord(ch) > 0x20:
                    want.add(ord(ch))
        got = set()
        for o in G.objects:
            if o['classID'] != 114:
                continue
            for _, vals in detect_runs(obj_payload(G, o), 64):
                got |= set(vals)
        miss = len(want - got)
        # 门槛说明：Makinas/Rii/Stick 被换成我们的字库后，并集不再包含那三个**日文原字体**的
        # 6356 汉字，缺字数从 85 回到「两份源字体都缺的冷门码位」量级（约 850，都是
        # Latin-Extended/标点等不在游戏文本里的字符）。所以这里判定 < 1000。
        assert miss < 1000, f'缺字 {miss} 偏多'
        return f'charset={len(want)} baked={len(got)} missing={miss}'
    check('coverage vs charset.txt', t_coverage)

    # 7. 自研 bundle 提取器的 SerializedFile 可解析（version 串非对齐坑）
    def t_our():
        if not os.path.exists(a.our):
            return 'skip（没有 --our 文件）'
        O = UnityFile(a.our, verbose=False)
        assert len(O.objects) == 7, f'对象数 {len(O.objects)} != 7'
        return f'objects={len(O.objects)} unity={O.unity_version!r} metadataStart={O._types_pos}'
    check('UnityFile(our bundle serialized)', t_our)

    # 8. 参考文件（补丁备份）可解析
    def t_ref():
        if not os.path.exists(a.ref):
            return 'skip（没有 ref 文件）'
        R = UnityFile(a.ref, verbose=False)
        return f'objects={len(R.objects)}'
    check('UnityFile(patch backup)', t_ref)

    print('\n=== 自检结果 ===')
    bad = 0
    for ok, name, msg in RESULTS:
        print(f'  [{"PASS" if ok else "FAIL"}] {name}: {msg}')
        bad += 0 if ok else 1
    print(f'=> {len(RESULTS) - bad}/{len(RESULTS)} 通过')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
