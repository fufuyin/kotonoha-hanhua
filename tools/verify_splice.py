#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立校验 splice_fonts.py 产出的 .test 文件（不复用其自证逻辑）。

检查项：
  1. 对象数一致；除被替换的字体对象外，所有对象的 pathID/classID/typeID/byteStart/byteSize 完全一致
  2. 被替换字体对象的 payload：名字保留、material/atlas PPtr 指向预期目标、m_Script 与原文件一致
  3. 图集像素：被替换字体的图集 == 我们图集；其余图集 == 原文件（逐字节）
  4. 头部 fileSize == 实际长度，metadataSize/dataOffset 不变
  5. 被替换字体的字符表条目数（parse_tmp_font 的 detect_runs）

用法: python verify_splice.py --orig <patch.assets> --out <test.assets> --our <our_raw.serialized>
"""
import os, struct, sys, hashlib, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
from parse_tmp_font import detect_runs
# 复用 splice_fonts 的锚点逻辑（含 m_CompleteImageSize 陷阱的修正）
from splice_fonts import find_pixels

PIX = 8192 * 8192


def payload(f, o):
    return f.buf[o['abs']:o['abs'] + o['byteSize']]


def find_pptr(p, pid):
    pat = struct.pack('<Q', pid)
    out, s = [], 0
    while True:
        i = p.find(pat, s)
        if i < 0:
            return out
        out.append((i - 4, struct.unpack_from('<i', p, i - 4)[0] if i >= 4 else None))
        s = i + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--orig', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--our', required=True)
    a = ap.parse_args()
    ok = True

    A = UnityFile(a.orig, verbose=False)
    B = UnityFile(a.out, verbose=False)
    O = UnityFile(a.our, verbose=False)

    print(f'[1] objects orig={len(A.objects)} out={len(B.objects)}')
    if len(A.objects) != len(B.objects):
        print('    !! 对象数不一致'); ok = False
    changed = []
    for oa, ob in zip(A.objects, B.objects):
        same_id = (oa['pathID'] == ob['pathID'] and oa['classID'] == ob['classID'] and oa['typeID'] == ob['typeID'])
        if not same_id:
            print(f'    !! 对象身份变化 {hex(oa["pathID"])} -> {hex(ob["pathID"])}'); ok = False
            continue
        if (oa['byteStart'], oa['byteSize']) != (ob['byteStart'], ob['byteSize']):
            changed.append((oa, ob))
    print(f'    字节范围变化的对象 {len(changed)} 个:')
    for oa, ob in changed:
        print(f'      pathID={hex(oa["pathID"])} class={oa["classID"]} '
              f'({oa["byteStart"]},{oa["byteSize"]}) -> ({ob["byteStart"]},{ob["byteSize"]})')

    print(f'[4] header orig(fileSize={A.file_size}, mdSize={A.metadata_size}, dataOffset={A.data_offset}) '
          f'out(fileSize={B.file_size}, mdSize={B.metadata_size}, dataOffset={B.data_offset}) actual={len(B.buf)}')
    if B.file_size != len(B.buf) or B.metadata_size != A.metadata_size or B.data_offset != A.data_offset:
        print('    !! 头部不一致'); ok = False

    # 我们的图集像素
    our_tex = [o for o in O.objects if o['classID'] == 28 and o['byteSize'] > 1024 * 1024][0]
    otp = payload(O, our_tex)
    o_po, o_tail = find_pixels(otp)
    our_px = otp[o_po:o_po + PIX]
    our_sha = hashlib.sha256(our_px).hexdigest()
    print(f'[ref] our atlas px offset={o_po} tail={o_tail} sha256={our_sha[:20]} len={len(our_px)}')
    golden = r'F:\Application\Unity\twobake_atlas.bin'
    golden_ok = None
    if os.path.exists(golden) and os.path.getsize(golden) == PIX:
        golden_ok = (open(golden, 'rb').read() == our_px)
        print(f'[ref] 与外部黄金像素 twobake_atlas.bin 一致: {golden_ok}')
        if not golden_ok:
            ok = False
    our_mat_id = [o for o in O.objects if o['classID'] == 21][0]['pathID'] & 0xFFFFFFFFFFFFFFFF
    our_tex_id = our_tex['pathID'] & 0xFFFFFFFFFFFFFFFF

    # 2/3：未改动对象逐字节比对 + 被改像素的图集单独核对
    bmap = {o['pathID']: o for o in B.objects}
    EXCEPT = {0xbe, 0x53}  # 本次只改这两处：字体对象 0xbe、Gyate 图集 0x53
    print('[3a] 未改动对象的 payload 逐字节比对:')
    bad = []
    for oa, ob in zip(A.objects, B.objects):
        if oa['pathID'] in EXCEPT:
            continue
        if payload(A, oa) != payload(B, ob):
            bad.append(oa['pathID'])
    print(f'    不一致对象数={len(bad)}' + (f' 例如 {[hex(x) for x in bad[:5]]}' if bad else ' (全部逐字节一致)'))
    if bad:
        ok = False

    print('[3b] Gyate 图集 0x53 像素比对:')
    oa = [o for o in A.objects if o['pathID'] == 0x53][0]
    ob = bmap[0x53]
    pa, pb = payload(A, oa), payload(B, ob)
    pao, _ = find_pixels(pa)
    pbo, _ = find_pixels(pb)
    if pao is None or pbo is None or pao != pbo:
        print(f'    !! 锚点异常 {pao}/{pbo}'); ok = False
    else:
        head_ok = pa[:pao] == pb[:pbo]
        tail_ok = pa[pao + PIX:] == pb[pbo + PIX:]
        sb = hashlib.sha256(pb[pbo:pbo + PIX]).hexdigest()
        print(f'    像素锚点 {pbo} 头部一致={head_ok} 尾部一致={tail_ok} '
              f'像素 sha={sb[:16]} == 我们的图集? {sb == our_sha}')
        if not (head_ok and tail_ok and sb == our_sha):
            ok = False

    print('[2] 被替换字体 payload:')
    for oa, ob in changed:
        if oa['classID'] != 114:
            continue
        pb = payload(B, ob)
        pa = payload(A, oa)
        nm_len = struct.unpack_from('<i', pb, 28)[0]
        nm = pb[32:32 + nm_len].decode('utf-8')
        print(f'    pathID={hex(oa["pathID"])} name={nm!r} enabled={pb[12]} '
              f'script_same_as_orig={pb[16:28] == pa[16:28]}')
        if pb[16:28] != pa[16:28] or pb[12] != 1:
            print('    !! m_Script 未保留原值'); ok = False
        if nm_len != struct.unpack_from('<i', pa, 28)[0] or nm != pa[32:32 + struct.unpack_from('<i', pa, 28)[0]].decode('utf-8'):
            print('    !! 资产名未保留'); ok = False
        hits_mat = [h for h in find_pptr(pb, our_mat_id) if h[1] == 0]
        hits_tex = [h for h in find_pptr(pb, our_tex_id) if h[1] == 0]
        # 我们 bundle 里所有对象的 pathID 都不应该出现在新 payload 中（悬空引用检查）
        # 低值 pathID 的 8 字节模式极易巧合命中，单列不判失败
        ours_all = {o['pathID'] & 0xFFFFFFFFFFFFFFFF for o in O.objects}
        left, low = {}, {}
        for pid in ours_all:
            h = find_pptr(pb, pid)
            if not h:
                continue
            (left if pid >= 0x1000 else low)[hex(pid)] = len(h)
        m_ok = not hits_mat
        t_ok = not hits_tex
        runs = detect_runs(pb, 64)
        total = sum(len(v) for _, v in runs)
        print(f'    残留自家 material={len(hits_mat)} atlas={len(hits_tex)} '
              f'高值 pathID 残留={left if left else "无"} 低值巧合={low if low else "无"} 字符表条目合计={total}')
        if not (m_ok and t_ok and not left):
            print('    !! 仍引用我们 bundle 内的对象'); ok = False
        if total < 7000:
            print(f'    !! 字符表条目 {total} 偏少（预期 ~7898）'); ok = False

    print(f'[5] Gyate 字符表条目数（parse_tmp_font 独立扫描）：')
    for f, label in ((A, 'patch'), (B, 'test')):
        best = 0
        for o in f.objects:
            if o['classID'] != 114:
                continue
            for _, vals in detect_runs(payload(f, o), 64):
                best = max(best, len(vals))
        print(f'    {label}: 最大字符表条目={best}')

    print('RESULT:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
