#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把自家 bundle 的 TMP 字体资产 + 图集像素，拼接进游戏原补丁的 sharedassets0.assets（生成 .test 文件）。

原理（已逐字段验证）：
  TMP_FontAsset 的序列化布局 = [m_GameObject PPtr(12)][m_Enabled u8+3pad][m_Script PPtr(12)]
  [m_Name 字符串][TMP_Asset: hashCode(i32)/material(PPtr12)/materialHashCode(i32)]
  [TMP_FontAsset: m_Version(字符串) ... m_AtlasTextures(List<PPtr>) ...]
  两边的固定字段布局同构，只有 PPtr 指向不同 → 只需替换 3 个 PPtr 目标 + 保留原资产名。

不变式（必须成立）：
  * 目标文件对象数不变（不新增/删除对象），只把字体对象的 byteStart/byteSize 指向文件尾新数据
  * 图集像素原地覆盖（尺寸不变）→ 材质↔图集配对关系由 PPtr 保持不变
  * 每个字体资产仍用自己的材质（保留描边/颜色），必要时只把该材质 _MainTex 改指到我们写入像素的那张图集

用法:
  python splice_fonts.py --target <sharedassets0.assets> --our <our_raw.serialized>
                         [--out <sharedassets0.test.assets>] [--probe]
"""
import os, struct, sys, argparse, hashlib

try:  # 控制台是 GBK，避免非 GBK 字符直接崩
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile

PPTR = 12
WH = 8192
PIX = WH * WH  # 67108864


def u32(b, o):
    return struct.unpack_from('<i', b, o)[0]


def parse_head(p):
    """返回 (name, name_end, script_bytes)。布局见文件头注释。"""
    assert p[12] == 1, f'm_Enabled != 1: {p[12]}'
    name_len = u32(p, 28)
    name = p[32:32 + name_len].decode('utf-8')
    name_end = (28 + 4 + name_len + 3) & ~3
    return name, name_end, bytes(p[16:28])


def find_pptr(p, pid):
    """精确找 (i32 fileID, i64 pathID) 里 pathID==pid 的位置，返回 [(off_of_fileID, fileID)]。"""
    pat = struct.pack('<Q', pid)
    out = []
    s = 0
    while True:
        i = p.find(pat, s)
        if i < 0:
            break
        if i >= 4:
            out.append((i - 4, u32(p, i - 4)))
        s = i + 1
    return out


def find_pixels(p, pix=PIX):
    """定位 Texture2D 的像素起始偏移（已用外部黄金像素 twobake_atlas.bin 标定）。

    坑 1：m_CompleteImageSize 的值恰好也等于 8192*8192，不能取第一个匹配。
    坑 2：真锚点的判别特征是「其后恰好 12 字节全零（m_StreamData: u64 offset=0 + u32 size=0），
          且锚点前 4 字节为零（m_PlatformBlob 计数=0）」。
    实测：我们 bundle +0x04=104，补丁 0x52/0x53=+108（差 4 字节 = 资产名长度差）。
    """
    pat = struct.pack('<i', pix)
    cands, s = [], 0
    while True:
        i = p.find(pat, s)
        if i < 0:
            break
        cands.append(i)
        s = i + 1
    for i in reversed(cands):
        t = i + 4 + pix
        if t > len(p):
            continue
        tail = p[t:]
        if len(tail) == 12 and tail == b'\x00' * 12 and i >= 4 and p[i - 4:i] == b'\x00' * 4:
            return i + 4, dict(kind='inline', tail_len=12)
        # 兼容带 .resS 路径的写法：u64 offset + u32 size + i32 pathLen + path
        if 16 <= len(tail) <= 512:
            off, size, plen = struct.unpack_from('<qii', tail, 0)
            if 0 <= plen <= 200 and 16 + plen <= len(tail) and len(tail) - (16 + plen) <= 3 \
                    and all(32 <= c < 127 for c in tail[16:16 + plen]):
                return i + 4, dict(kind='stream', stream_offset=off, stream_size=size,
                                   path=tail[16:16 + plen].decode('ascii', 'replace'))
    return None, None


def obj_payload(f, o):
    return f.buf[o['abs']:o['abs'] + o['byteSize']]


def name_of_tex(p):
    for off in (0, 4):
        n = u32(p, off)
        if 1 <= n <= 80:
            try:
                s = p[off + 4:off + 4 + n].decode('utf-8')
                if s.isprintable():
                    return s
            except UnicodeDecodeError:
                pass
    return '?'


def name_of_mat(p):
    for off in (4, 0):
        n = u32(p, off)
        if 1 <= n <= 80:
            try:
                s = p[off + 4:off + 4 + n].decode('utf-8')
                if s.isprintable():
                    return s
            except UnicodeDecodeError:
                pass
    return '?'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--target', required=True)
    ap.add_argument('--our', required=True)
    ap.add_argument('--out', default=None)
    ap.add_argument('--probe', action='store_true')
    ap.add_argument('--report', default=None)
    ap.add_argument('--fonts', default='Gyate-Luminescence SDF',
                    help='要替换的字体资产名前缀，逗号分隔（默认只换 Gyate，与补丁作者改动同构）')
    a = ap.parse_args()

    rep = []
    def log(s):
        print(s)
        rep.append(s)

    tf = UnityFile(a.target, verbose=False)
    of = UnityFile(a.our, verbose=False)
    log(f'[target] {os.path.basename(a.target)} len={len(tf.buf)} objects={len(tf.objects)} dataOffset={tf.data_offset}')

    # ---------- 我们的资产 ----------
    our_font = [o for o in of.objects if o['classID'] == 114]
    our_tex = [o for o in of.objects if o['classID'] == 28]
    our_mat = [o for o in of.objects if o['classID'] == 21]
    assert len(our_font) == 1 and len(our_tex) == 1 and len(our_mat) == 1, 'our bundle shape unexpected'
    our_font, our_tex, our_mat = our_font[0], our_tex[0], our_mat[0]
    fp = obj_payload(of, our_font)
    tp_ = obj_payload(of, our_tex)
    mp = obj_payload(of, our_mat)

    our_name, our_name_end, our_script = parse_head(fp)
    our_mat_id = our_mat['pathID'] & 0xFFFFFFFFFFFFFFFF
    our_tex_id = our_tex['pathID'] & 0xFFFFFFFFFFFFFFFF
    log(f'[ours] font={our_name!r} size={our_font["byteSize"]} mat_id={our_mat_id:016x} tex_id={our_tex_id:016x}')

    mat_hits = find_pptr(fp, our_mat_id)
    tex_hits = find_pptr(fp, our_tex_id)
    log(f'[ours] payload 内 material PPtr 命中={mat_hits}  atlas PPtr 命中={tex_hits}')
    assert len(mat_hits) == 1 and len(tex_hits) == 1, 'PPtr 命中数不是 1，停止（可能有假阳性）'
    mat_off, atlas_off = mat_hits[0][0], tex_hits[0][0]

    px_off, px_tail = find_pixels(tp_)
    assert px_off is not None, 'our atlas 里找不到像素数组长度字段'
    our_px = tp_[px_off:px_off + PIX]
    assert len(our_px) == PIX
    log(f'[ours] atlas pixel offset={px_off} tail={px_tail}')
    log(f'[ours] atlas pixel sha256={hashlib.sha256(our_px).hexdigest()[:16]}')
    golden = r'F:\Application\Unity\twobake_atlas.bin'
    if os.path.exists(golden) and os.path.getsize(golden) == PIX:
        g = open(golden, 'rb').read()
        same = (g == our_px)
        log(f'[ours] 与外部黄金像素 twobake_atlas.bin 一致: {same}')
        assert same, '我们的图集像素与 twobake_atlas.bin 不一致 —— 锚点错了'

    # ---------- 目标资产清单 ----------
    t_fonts, t_tex, t_mats = [], [], []
    for o in tf.objects:
        p = obj_payload(tf, o)
        if o['classID'] == 114:
            nm, ne, sc = parse_head(p)
            t_fonts.append((o, p, nm, sc))
        elif o['classID'] == 28 and o['byteSize'] > 1024 * 1024:
            t_tex.append((o, p, name_of_tex(p)))
        elif o['classID'] == 21:
            t_mats.append((o, p, name_of_mat(p)))
    log(f'[target] 字体 {len(t_fonts)} 个: ' + ', '.join(f'{nm}({o["byteSize"]})' for o, _, nm, _ in t_fonts))
    log(f'[target] 大图集 {len(t_tex)} 张: ' + ', '.join(f'{nm}[0x{o["pathID"] & 0xFFFFFFFFFFFFFFFF:x}]{o["byteSize"]}' for o, _, nm in t_tex))

    sel = [s.strip() for s in a.fonts.split(',') if s.strip()]
    mat_by_name = {nm: o for o, _, nm in t_mats}
    tex_by_name = {nm: o for o, _, nm in t_tex}

    def selected(nm):
        return any(nm.startswith(pfx) for pfx in sel)

    out = bytearray(tf.buf)
    changes = []

    # ---------- 1) 图集像素原地覆盖（只覆盖所选字体的 8192² 图集） ----------
    target_tex_ids = {}
    for o, p, nm in t_tex:
        if not selected(nm):
            log(f'[keep] 图集 {nm} 不属于所选字体，保持原样')
            continue
        po, ptail = find_pixels(p)
        if po is None or o['byteSize'] - po < PIX:
            log(f'[skip] 图集 {nm} 尺寸 {o["byteSize"]} 容纳不下 8192x8192 像素 (anchor={po})')
            continue
        if not a.probe:
            out[o['abs'] + po:o['abs'] + po + PIX] = our_px
        target_tex_ids[nm] = o['pathID'] & 0xFFFFFFFFFFFFFFFF
        changes.append(f'atlas {nm}: pixels @abs+{po} <- ours')
        log(f'[plan] 覆盖图集像素 {nm} (0x{o["pathID"] & 0xFFFFFFFFFFFFFFFF:x}) abs+{po} tail={ptail}')

    # ---------- 2) 字体资产替换（追加到文件尾 + 改对象表） ----------
    if not a.probe:
        # 先算好每个字体需要的新 payload
        pass
    new_font_blobs = []
    for o, tp, tname, tscript in t_fonts:
        if not selected(tname):
            log(f'[keep] 字体 {tname!r} 不在替换列表，保持原样（不新增/不修改）')
            continue
        base = tname  # 目标资产名作为查找键，如 'Gyate-Luminescence SDF'
        mat_name = base + ' Material'
        mat_obj = mat_by_name.get(mat_name)
        if mat_obj is None:
            log(f'[warn] 找不到材质 {mat_name!r}，跳过 {tname!r}')
            continue
        # 该字体用哪张图集：名字里含 Atlas 的、前缀匹配目标布局；Gyate/Makinas 用自家图集，其余用 Gyate 的
        atlas_obj = None
        for nm, to in tex_by_name.items():
            if not (nm.startswith(base) and nm.endswith('Atlas')):
                continue
            po2, _ = find_pixels(obj_payload(tf, to))
            if po2 is not None and (to['byteSize'] - po2) >= PIX:
                atlas_obj = to
                break
        if atlas_obj is None:
            # Rii/Stick 的 4096² 图集装不下 → 指向 Gyate 图集（其像素已是我们的）
            g = tex_by_name.get('Gyate-Luminescence SDF Atlas')
            assert g is not None, '找不到 Gyate 图集作为共用图集'
            atlas_obj = g
        atlas_id = atlas_obj['pathID'] & 0xFFFFFFFFFFFFFFFF
        mat_id = mat_obj['pathID'] & 0xFFFFFFFFFFFFFFFF

        tname_len = u32(tp, 28)
        tname_end = (28 + 4 + tname_len + 3) & ~3
        shift = tname_end - our_name_end
        new = bytearray(fp[0:12]) + bytearray(tp[12:tname_end]) + bytearray(fp[our_name_end:])
        m_off = mat_off + shift
        a_off = atlas_off + shift
        struct.pack_into('<i', new, m_off, 0)
        struct.pack_into('<Q', new, m_off + 4, mat_id)
        struct.pack_into('<i', new, a_off, 0)
        struct.pack_into('<Q', new, a_off + 4, atlas_id)
        # m_FontWeightTable 与末尾字段采用目标原值：
        # 实测尾部布局 [-272: i32 count=10][-268:-28: 10×TMP_FontWeightPair(24B)=240B]
        #               [-28:-16: 一个 null PPtr][-16: 0.75f,7.0f,35,10]
        # 我们的工程资产把权重表全填成了自己(指向 bundle 内 pathID)，搬过去就是悬空引用。
        assert len(tp) >= 272 and len(new) >= 272, 'payload 太短，权重表假设不成立'
        assert tp[-16:] == fp[-16:], '尾部 16B 结构不一致'
        assert struct.unpack_from('<i', tp, len(tp) - 272)[0] == 10, '目标权重表计数异常'
        assert struct.unpack_from('<i', fp, len(fp) - 272)[0] == 10, '我们权重表计数异常'
        new[-268:-28] = tp[-268:-28]
        new_font_blobs.append((o, bytes(new), tname, mat_id, atlas_id))
        log(f'[plan] 字体 {tname!r} (0x{o["pathID"] & 0xFFFFFFFFFFFFFFFF:x}, {o["byteSize"]}B) '
            f'-> 新 payload {len(new)}B, material=0x{mat_id:x}, atlas=0x{atlas_id:x} (shift={shift})')

    # ---------- 3) Rii/Stick 材质 _MainTex 改指共享图集 ----------
    redirect_targets = {}
    for nm, to in tex_by_name.items():
        if not selected(nm):
            continue
        po, _ = find_pixels(obj_payload(tf, to))
        if po is not None and (to['byteSize'] - po) >= PIX:
            continue  # 8192x8192 已写入我们像素，不需要改材质
        redirect_targets[to['pathID'] & 0xFFFFFFFFFFFFFFFF] = nm
    shared_id = target_tex_ids.get('Gyate-Luminescence SDF Atlas')
    for o, p, nm in t_mats:
        for old_id, old_nm in redirect_targets.items():
            hits = [h for h in find_pptr(p, old_id) if h[1] == 0]
            if hits:
                if len(hits) != 1:
                    log(f'[warn] 材质 {nm} 命中 {old_nm} 的 PPtr {len(hits)} 处，跳过')
                    continue
                off = o['abs'] + hits[0][0] + 4
                if not a.probe:
                    struct.pack_into('<Q', out, off, shared_id)
                changes.append(f'material {nm}: _MainTex 0x{old_id:x} -> 0x{shared_id:x}')
                log(f'[plan] 材质 {nm}: _MainTex -> 0x{shared_id:x} (@abs+{hits[0][0]})')
                break

    # ---------- 4) 写文件 ----------
    if not a.probe:
        if not new_font_blobs:
            log('[abort] 没有可写的字体，未输出')
        else:
            # 对象表条目位置：每个 20 字节
            entry_pos = {}
            for o, blob, tname, mat_id, atlas_id in new_font_blobs:
                if len(out) % 16:
                    out += b'\0' * (16 - len(out) % 16)
                abs_ = len(out)
                out += blob
                i = tf.objects.index(o)
                ep = tf._objects_pos + i * 20
                struct.pack_into('<I', out, ep + 8, abs_ - tf.data_offset)
                struct.pack_into('<I', out, ep + 12, len(blob))
                entry_pos[tname] = (ep, abs_, len(blob))
                log(f'[write] {tname!r} -> abs={abs_} byteStart={abs_ - tf.data_offset} byteSize={len(blob)} entry@{ep}')
            struct.pack_into('>I', out, 4, len(out))
            log(f'[write] fileSize header -> {len(out)}')

    # ---------- 5) 校验 ----------
    if not a.probe:
        chk = UnityFile.__new__(UnityFile)
        chk.buf = bytes(out)
        chk.path = a.out or '<mem>'
        chk.verbose = False
        chk._read_header()
        chk._read_metadata()
        log(f'[verify] 重解析 out: objects={len(chk.objects)} valid={chk._objects_valid} '
            f'fileSize_hdr={chk.file_size} actual={len(out)}')
        assert len(chk.objects) == len(tf.objects)
        for o, blob, tname, mat_id, atlas_id in new_font_blobs:
            no = [x for x in chk.objects if x['pathID'] == o['pathID']][0]
            assert no['byteSize'] == len(blob)
            np_ = obj_payload(chk, no)
            nm2, ne2, sc2 = parse_head(np_)
            mh = find_pptr(np_, mat_id)
            ah = find_pptr(np_, atlas_id)
            log(f'[verify] {tname!r}: name={nm2!r} size={no["byteSize"]} mat_hit={len(mh)} atlas_hit={len(ah)}')
            assert nm2 == tname and len(mh) >= 1 and len(ah) >= 1
            # 不允许残留我们 bundle 自己的 pathID
            for bad, label in ((our_mat_id, 'our material'), (our_tex_id, 'our atlas')):
                assert not find_pptr(np_, bad), f'{tname}: 仍残留 {label} 引用'
        if a.out:
            open(a.out, 'wb').write(bytes(out))
            log(f'[out] {a.out} ({len(out)} bytes)')
    else:
        log('[probe] 未写出任何文件')

    if a.report:
        open(a.report, 'w', encoding='utf-8').write('\n'.join(rep))
        print('report ->', a.report)


if __name__ == '__main__':
    main()
