#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第二批资产级修改（在已装好的 Gyate 修复之上）：
  A. sharedassets0.assets
     * Makinas 图集 0x52 像素 <- 我们的（它本来就是 8192²，材质口径已一致，无需改材质）
     * Makinas/Rii/Stick 字体资产 0xbf/0xc0/0xc1 换成我们的 payload
       （各用自己的基础材质 0x1b/0x1c/0x1d；Rii/Stick 图集是 4096² -> 指向 0x53）
     * Rii/Stick 相关材质：_MainTex->0x53，并按公式重定向 SDF 几何参数
         _GradientScale = padding+1 = 11
         _ScaleRatioA   = 1 - 1/_GradientScale = 0.909091
         _ScaleRatioB/C = _ScaleRatioA * (0.8125 - _FaceDilate)   （由原版 4 组数据反推验证）
     * Gyate 基础材质 0x1a：_OutlineWidth 0.3 -> 0.15（用户要求金币描边降低）
  B. resources.assets
     * GDhwGoJA 图集 0x1ff3：像素在 resources.assets.resS 的 (851443740, 67108864) 原地覆盖
     * GDhwGoJA 字体 0x80b9 换成我们的 payload（atlas->0x1ff3, material->0x78）

用法:
  python splice_more.py --shared <live.assets> --shared-out <out> \
                        --res <live resources.assets> --res-out <out> \
                        --our <our_raw.serialized> --golden <twobake_atlas.bin> [--probe]
"""
import os, struct, sys, argparse, hashlib

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile
from splice_fonts import parse_head, find_pptr, find_pixels, obj_payload

PIX = 8192 * 8192
PADDING = 10
GRAD = PADDING + 1           # 11
RATIO_A = 1.0 - 1.0 / GRAD   # 0.909091
GD_RES_OFFSET = 851443740    # resources.assets.resS 里 GDhwGoJA 图集的像素起点
GD_RES_SIZE = PIX


def u32(b, o):
    return struct.unpack_from('<i', b, o)[0]


def f32(b, o):
    return struct.unpack_from('<f', b, o)[0]


def find_prop_float(p, name):
    """返回属性名后面的 float 值偏移（m_Floats 项：字符串 + float）。"""
    pat = name.encode()
    i = 0
    while True:
        i = p.find(pat, i)
        if i < 0:
            return None
        if i >= 4:
            n = u32(p, i - 4)
            if n == len(name):
                return (i + len(name) + 3) & ~3
        i += 1


def find_prop_pptr(p, name):
    """返回属性名后面的 PPtr fileID 偏移（m_TexEnvs 项：字符串 + PPtr(12)）。"""
    off = find_prop_float(p, name)
    return off


def patch_float(buf, abs_off, value):
    struct.pack_into('<f', buf, abs_off, value)


def patch_pptr(buf, abs_off, path_id):
    struct.pack_into('<i', buf, abs_off, 0)
    struct.pack_into('<Q', buf, abs_off + 4, path_id)


class Editor:
    def __init__(self, path):
        self.path = path
        self.f = UnityFile(path, verbose=False)
        self.buf = bytearray(self.f.buf)
        self.log = []

    def obj(self, path_id):
        for o in self.f.objects:
            if (o['pathID'] & 0xFFFFFFFFFFFFFFFF) == path_id:
                return o
        raise KeyError(hex(path_id))

    def payload(self, o):
        return self.f.buf[o['abs']:o['abs'] + o['byteSize']]

    def patch_bytes(self, abs_off, data):
        self.buf[abs_off:abs_off + len(data)] = data

    def add_font(self, obj, new_payload):
        """追加到文件尾并改对象表（与 splice_fonts 相同的技术）。"""
        if len(self.buf) % 16:
            self.buf += b'\x00' * (16 - len(self.buf) % 16)
        abs_ = len(self.buf)
        self.buf += new_payload
        i = self.f.objects.index(obj)
        ep = self.f._objects_pos + i * 20
        struct.pack_into('<I', self.buf, ep + 8, abs_ - self.f.data_offset)
        struct.pack_into('<I', self.buf, ep + 12, len(new_payload))
        self.log.append(f'font {hex(obj["pathID"] & 0xFFFFFFFFFFFFFFFF)} -> abs={abs_} size={len(new_payload)}')
        return abs_

    def finish(self):
        struct.pack_into('>I', self.buf, 4, len(self.buf))
        return bytes(self.buf)


def weight_table_offset(p):
    """定位 m_FontWeightTable 的 240 字节数据起点。

    实测：我们/补丁 Gyate/Rii/Stick 的 count=10 在 len-272；
    原版 Makinas/GDhwGoJA 在 len-268（尾部数据长度差 4，字段集相同）→ 就近搜索，勿用固定偏移。
    """
    for off in (len(p) - 272, len(p) - 268):
        if 0 <= off and u32(p, off) == 10:
            return off + 4
    return None


def build_font_payload(our_payload, target_payload, our_name_end, our_mat_off, our_atlas_off,
                       atlas_id, mat_id):
    """目标头 + 目标名字 + 我们的其余字段，并把 material/atlas PPtr 指向目标。"""
    tname_len = u32(target_payload, 28)
    tname_end = (28 + 4 + tname_len + 3) & ~3
    shift = tname_end - our_name_end
    new = bytearray(our_payload[0:12]) + bytearray(target_payload[12:tname_end]) + bytearray(our_payload[our_name_end:])
    struct.pack_into('<i', new, our_mat_off + shift, 0)
    struct.pack_into('<Q', new, our_mat_off + shift + 4, mat_id)
    struct.pack_into('<i', new, our_atlas_off + shift, 0)
    struct.pack_into('<Q', new, our_atlas_off + shift + 4, atlas_id)
    # 固定字段（权重表）照抄目标，避免指向我们 bundle 的悬空引用
    off_t = weight_table_offset(target_payload)
    off_o = weight_table_offset(our_payload)
    assert off_t is not None, '目标权重表定位失败'
    assert off_o is not None, '我们权重表定位失败'
    assert target_payload[-16:] == our_payload[-16:], '尾部 16B 不一致'
    new[off_o + shift:off_o + shift + 240] = target_payload[off_t:off_t + 240]
    return bytes(new)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--shared', required=True)
    ap.add_argument('--shared-out', required=True)
    ap.add_argument('--res', required=True)
    ap.add_argument('--res-out', required=True)
    ap.add_argument('--our', required=True)
    ap.add_argument('--golden', required=True)
    ap.add_argument('--outline-gyate', type=float, default=0.15)
    ap.add_argument('--skip-res', action='store_true', help='只做 sharedassets0（不动 resources.assets/.resS）')
    ap.add_argument('--probe', action='store_true')
    a = ap.parse_args()

    golden = open(a.golden, 'rb').read()
    assert len(golden) == PIX
    gsha = hashlib.sha256(golden).hexdigest()

    O = UnityFile(a.our, verbose=False)
    our_font = [o for o in O.objects if o['classID'] == 114][0]
    our_payload = obj_payload(O, our_font)
    our_name, our_name_end, _ = parse_head(our_payload)
    our_tex = [o for o in O.objects if o['classID'] == 28][0]
    our_mat = [o for o in O.objects if o['classID'] == 21][0]
    our_mat_off = find_pptr(our_payload, our_mat['pathID'] & 0xFFFFFFFFFFFFFFFF)[0][0]
    our_atlas_off = find_pptr(our_payload, our_tex['pathID'] & 0xFFFFFFFFFFFFFFFF)[0][0]
    print(f'[ours] name={our_name!r} payload={len(our_payload)} mat_off={our_mat_off} atlas_off={our_atlas_off}')
    print(f'[ours] golden sha256={gsha[:16]}')

    # ---------------- A. sharedassets0 ----------------
    E = Editor(a.shared)
    print(f'[A] {os.path.basename(a.shared)} objects={len(E.f.objects)} len={len(E.buf)}')

    # A1. Makinas 图集 0x52 原地像素
    for pid, label in ((0x52, 'Makinas'),):
        o = E.obj(pid)
        po, tail = find_pixels(E.payload(o))
        assert po is not None and o['byteSize'] - po >= PIX, f'{label} 图集装不下'
        if not a.probe:
            E.patch_bytes(o['abs'] + po, golden)
        print(f'[A1] 图集 {label} 0x{pid:x} 像素 <- golden @payload+{po} tail={tail}')

    # A2. 字体替换
    fonts = [('Makinas-4-Square SDF', 0xbf, 0x52, 0x1b),
             ('RiiPopkkR SDF', 0xc0, 0x53, 0x1c),
             ('Stick_Regular SDF', 0xc1, 0x53, 0x1d)]
    for name, fpid, apid, mpid in fonts:
        fo = E.obj(fpid)
        tp = E.payload(fo)
        tname_len = u32(tp, 28)
        tname = tp[32:32 + tname_len].decode('utf-8')
        assert tname == name, f'字体名不符 {tname!r} != {name!r}'
        new = build_font_payload(our_payload, tp, our_name_end, our_mat_off, our_atlas_off, apid, mpid)
        print(f'[A2] {name} 0x{fpid:x} -> payload {len(new)}B atlas=0x{apid:x} material=0x{mpid:x}')
        if not a.probe:
            E.add_font(fo, new)

    # A3. Rii/Stick 材质重定向（找所有引用 0x1e/0x1f 图集的材质）
    old_atlas_ids = {0x1e, 0x1f}
    n_mat = 0
    for o in E.f.objects:
        if o['classID'] != 21:
            continue
        p = E.payload(o)
        hit = None
        for aid in old_atlas_ids:
            h = [x for x in find_pptr(p, aid) if x[1] == 0]
            if len(h) == 1:
                hit = (aid, h[0][0])
                break
        if hit is None:
            continue
        aid, off = hit
        fd = find_prop_float(p, '_FaceDilate')
        face_dilate = f32(p, fd) if fd is not None else 0.0
        ratio_bc = RATIO_A * (0.8125 - face_dilate)
        vals = {'_GradientScale': GRAD, '_TextureWidth': float(8192), '_TextureHeight': float(8192),
                '_ScaleRatioA': RATIO_A, '_ScaleRatioB': ratio_bc, '_ScaleRatioC': ratio_bc}
        if not a.probe:
            E.patch_bytes(o['abs'] + off, struct.pack('<i', 0) + struct.pack('<Q', 0x53))
            for k, v in vals.items():
                fo2 = find_prop_float(p, k)
                if fo2 is None:
                    print(f'    !! 材质 {hex(o["pathID"] & 0xFFFFFFFFFFFFFFFF)} 缺属性 {k}')
                    continue
                struct.pack_into('<f', E.buf, o['abs'] + fo2, v)
        n_mat += 1
        print(f'[A3] 材质 0x{o["pathID"] & 0xFFFFFFFFFFFFFFFF:x} 引用图集 0x{aid:x} -> 0x53; '
              f'FaceDilate={face_dilate:g} ScaleRatioB/C={ratio_bc:.6f}')
    print(f'[A3] 共 {n_mat} 个材质')

    # A4. Gyate 基础材质 0x1a 描边降低
    o1a = E.obj(0x1a)
    p1a = E.payload(o1a)
    off_ow = find_prop_float(p1a, '_OutlineWidth')
    old_ow = f32(p1a, off_ow)
    if not a.probe:
        struct.pack_into('<f', E.buf, o1a['abs'] + off_ow, a.outline_gyate)
    print(f'[A4] Gyate 材质 0x1a _OutlineWidth {old_ow:g} -> {a.outline_gyate:g}')

    if a.skip_res:
        if not a.probe:
            open(a.shared_out, 'wb').write(E.finish())
            print(f'[out] {a.shared_out} ({os.path.getsize(a.shared_out)} bytes)')
        else:
            print('[probe] 未写出任何文件')
        print('[skip-res] 只做 sharedassets0，未触碰 resources.assets/.resS')
        return

    # ---------------- B. resources.assets ----------------
    R = Editor(a.res)
    print(f'[B] {os.path.basename(a.res)} objects={len(R.f.objects)} len={len(R.buf)}')
    gd = R.obj(0x80b9)
    tp = R.payload(gd)
    tname_len = u32(tp, 28)
    tname = tp[32:32 + tname_len].decode('utf-8')
    print(f'[B1] 字体 {tname!r} 0x80b9 size={gd["byteSize"]}')
    assert tname == 'GDhwGoJA-OTF112b2 SDF', tname
    new_gd = build_font_payload(our_payload, tp, our_name_end, our_mat_off, our_atlas_off, 0x1ff3, 0x78)
    print(f'[B1] -> payload {len(new_gd)}B atlas=0x1ff3 material=0x78')
    if not a.probe:
        R.add_font(gd, new_gd)

    # B2. .resS 像素原地覆盖
    res_path = a.res + '.resS'
    print(f'[B2] .resS 覆盖 @{GD_RES_OFFSET} size={GD_RES_SIZE}  ({os.path.basename(res_path)})')
    if not a.probe:
        with open(res_path, 'r+b') as fh:
            fh.seek(GD_RES_OFFSET)
            fh.write(golden)
            fh.flush()
        print('     .resS 已写入')

    if a.probe:
        print('[probe] 未写出任何文件')
        return

    open(a.shared_out, 'wb').write(E.finish())
    open(a.res_out, 'wb').write(R.finish())
    for p in (a.shared_out, a.res_out):
        print(f'[out] {p} ({os.path.getsize(p)} bytes)')
    print('\n'.join(E.log))


if __name__ == '__main__':
    main()
