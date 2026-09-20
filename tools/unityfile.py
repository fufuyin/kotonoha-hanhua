#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unity 序列化文件（.assets / level*）解析器 —— 纯标准库实现。

本游戏实测特征（Unity 2019.1.13f1, SerializedFile version 19）：
  * 文件头 4 个 u32 为大端：metadataSize, fileSize, version, dataOffset
  * 头部之后（unityVersion 字符串起）全部为小端

用法:
  python unityfile.py <file> --info                  # 头部/类型/对象统计
  python unityfile.py <file> --types                 # 列出类型
  python unityfile.py <file> --textassets --stats    # TextAsset 统计
  python unityfile.py <file> --dump-texts <dir>      # 导出所有 TextAsset
  python unityfile.py <file> --find-name Story_00_00 # 按名查找
"""
import struct, sys, os, argparse, json, re

# ---------- 读取器 ----------
class R:
    def __init__(self, buf, pos=0, be=False):
        self.b = buf; self.p = pos; self.be = be
        self.e = '>' if be else '<'
    def u8(self):
        v = self.b[self.p]; self.p += 1; return v
    def i8(self):
        v = struct.unpack_from('b', self.b, self.p)[0]; self.p += 1; return v
    def bool(self):
        return self.u8() != 0
    def i16(self):
        v = struct.unpack_from(self.e + 'h', self.b, self.p)[0]; self.p += 2; return v
    def u16(self):
        v = struct.unpack_from(self.e + 'H', self.b, self.p)[0]; self.p += 2; return v
    def i32(self):
        v = struct.unpack_from(self.e + 'i', self.b, self.p)[0]; self.p += 4; return v
    def u32(self):
        v = struct.unpack_from(self.e + 'I', self.b, self.p)[0]; self.p += 4; return v
    def i64(self):
        v = struct.unpack_from(self.e + 'q', self.b, self.p)[0]; self.p += 8; return v
    def u64(self):
        v = struct.unpack_from(self.e + 'Q', self.b, self.p)[0]; self.p += 8; return v
    def raw(self, n):
        v = self.b[self.p:self.p+n]; self.p += n; return v
    def cstr(self):
        end = self.b.index(b'\0', self.p)
        s = self.b[self.p:end]; self.p = end + 1; return s
    def align(self, n=4):
        self.p = (self.p + n - 1) & ~(n - 1)
    def ustr(self):
        """Unity 字符串: i32 字节长度 + 字节 + 补齐到 4 字节"""
        n = self.i32()
        if n < 0 or self.p + n > len(self.b):
            raise ValueError(f'bad string length {n} at {self.p-4}')
        s = self.b[self.p:self.p+n]
        self.p += n
        self.p = (self.p + 3) & ~3
        return s

CLASS_NAMES = {
    1: 'GameObject', 4: 'Transform', 21: 'Material', 28: 'Texture2D', 43: 'Mesh',
    48: 'Shader', 49: 'TextAsset', 74: 'AnimationClip', 83: 'AudioClip',
    114: 'MonoBehaviour', 115: 'MonoScript', 128: 'Font', 142: 'AssetBundle',
    156: 'PrefabInstance', 213: 'Sprite', 222: 'CanvasRenderer', 223: 'Canvas',
    224: 'RectTransform', 225: 'CanvasGroup', 114: 'MonoBehaviour',
}

class UnityFile:
    def __init__(self, path, verbose=False):
        self.path = path
        self.buf = open(path, 'rb').read()
        self.verbose = verbose
        self._read_header()
        self._read_metadata()

    def _read_header(self):
        b = self.buf
        self.metadata_size, self.file_size, self.version, self.data_offset = struct.unpack_from('>IIII', b, 0)
        self.endian_flag = b[16]
        if self.version >= 22:
            raise NotImplementedError(f'version {self.version} 需要额外头部字段')
        r = R(b, 20)
        self.unity_version = r.cstr().decode('utf-8', 'replace')
        # 实测陷阱：bundle 内嵌 SerializedFile 的版本串可能不以 4 字节对齐结束
        # （本工程 raw bundle 里是 b'2019.1.13f1\n2'，13 字节）。此处若盲 align(4)，
        # 元数据起点会偏移 2 字节，target/typeTree/类型数全错，解析一路跑到文件尾。
        # 故记录两个候选起点，在 _read_metadata 里用「对象表全部落在文件内」判定。
        self._types_candidates = []
        for cand in (r.p, (r.p + 3) & ~3):
            if cand not in self._types_candidates:
                self._types_candidates.append(cand)
        self.target_platform = None
        self.enable_type_tree = None
        self._types_pos = self._types_candidates[0]
        if self.verbose:
            print(f'[HDR] mdSize={self.metadata_size} fileSize={self.file_size} ver={self.version} '
                  f'dataOffset={self.data_offset} endianFlag={self.endian_flag} unity={self.unity_version!r} '
                  f'actual={len(b)} candidates={self._types_candidates}')

    def _read_metadata(self):
        errs = []
        for pos in self._types_candidates:
            try:
                self._parse_metadata_at(pos)
            except Exception as ex:
                errs.append(f'{pos}: {ex}')
                continue
            if getattr(self, '_objects_valid', False):
                self._types_pos = pos
                if self.verbose:
                    print(f'[META] metadataStart={pos} target={self.target_platform} '
                          f'typeTree={self.enable_type_tree}')
                return
            errs.append(f'{pos}: object table out of file')
        raise ValueError('metadata parse failed: ' + ' | '.join(errs))

    def _parse_metadata_at(self, pos):
        r = R(self.buf, pos)
        self.target_platform = r.i32()
        self.enable_type_tree = r.bool()
        n = r.i32()
        if not (1 <= n <= 500):
            raise ValueError(f'bad type count {n}')
        self.types = []
        for i in range(n):
            t = {'classID': r.i32()}
            if self.version >= 16:
                t['isStripped'] = r.bool()
            if self.version >= 17:
                t['scriptTypeIndex'] = r.i16()
            if (self.version < 16 and t['classID'] < 0) or (self.version >= 16 and t['classID'] == 114):
                t['scriptID'] = r.raw(16).hex()
            if self.version >= 13:
                t['oldTypeHash'] = r.raw(16).hex()
            if self.enable_type_tree:
                t['typeTree'] = self._read_type_tree(r, t['classID'])
            self.types.append(t)
        self.obj_n = r.i32()
        r.align(4)   # 实测：对象条目表在 obj_n 之后按 4 字节对齐（否则 pathID/大小全部错位）
        self._objects_pos = r.p
        self.objects = None
        self._parse_objects(self._objects_pos)

    def _read_type_tree(self, r, class_id):
        node_n = r.i32()
        nodes = []
        for _ in range(node_n):
            node = {}
            node['version'] = r.u16()
            node['level'] = r.u8()
            node['typeFlags'] = r.u8()
            node['typeStrOffset'] = r.u32()
            node['nameStrOffset'] = r.u32()
            node['byteSize'] = r.i32()
            node['index'] = r.i32()
            node['metaFlag'] = r.i32()
            if self.version >= 19:
                node['refTypeHash'] = r.u64()
            nodes.append(node)
        str_buf_size = r.i32()
        str_buf = r.raw(str_buf_size)
        return {'nodes': nodes, 'stringBuffer': str_buf}

    def _parse_objects(self, pos):
        r = R(self.buf, pos)
        n = self.obj_n
        objs = []
        ok = True
        for i in range(n):
            try:
                o = {}
                o['pathID'] = r.i64() if self.version >= 14 else r.i32()
                o['byteStart'] = r.i64() if self.version >= 22 else r.u32()
                o['byteSize'] = r.u32()
                o['typeID'] = r.i32()
                if self.version < 16:
                    o['classID'] = r.i16()
                else:
                    o['classID'] = self.types[o['typeID']]['classID'] if 0 <= o['typeID'] < len(self.types) else -1
                if self.version < 17:
                    o['isDestroyed'] = r.u16()
                o['abs'] = o['byteStart'] + self.data_offset   # byteStart 相对数据段起始
                if not (0 <= o['abs'] <= len(self.buf)) or o['abs'] + o['byteSize'] > len(self.buf):
                    ok = False
                objs.append(o)
            except Exception as ex:
                ok = False
                break
        self.objects = objs
        self._objects_valid = ok
        if self.verbose:
            print(f'[META] types={len(self.types)} objects={n} parsed={len(objs)} valid={ok} objTablePos={pos}')
            if objs:
                bad = [o for o in objs[:5] if o['byteStart'] > len(self.buf)]
                print(f'[META] first objects: {[{k: (v if k!="pathID" else hex(v)) for k,v in o.items()} for o in objs[:3]]}')
                print(f'[META] max byteStart+size = {max((o["byteStart"]+o["byteSize"]) for o in objs)} filelen={len(self.buf)}')

    # -------- TextAsset --------
    def textassets(self):
        out = []
        for o in self.objects:
            if o['classID'] != 49:
                continue
            r = R(self.buf, o['abs'])
            try:
                name = r.ustr().decode('utf-8', 'replace')
                # m_Script 必须手工解析：ustr() 结束时指针已被 4 字节对齐，
                # 用 r.p - len 计算偏移会把对齐填充算进去（5525%4=1 → 偏 3 字节）
                script_len_field_off = r.p
                n = r.i32()
                if n < 0 or r.p + n > len(self.buf):
                    raise ValueError(f'bad script length {n}')
                script_off = r.p
                script = self.buf[script_off:script_off + n]
                r.p = script_off + n
                r.align(4)
            except Exception as e:
                out.append({'obj': o, 'error': str(e)})
                continue
            out.append({'obj': o, 'name': name, 'script': script,
                        'script_len_field_off': script_len_field_off, 'script_off': script_off,
                        'script_len': len(script)})
        return out

    def type_summary(self):
        from collections import Counter
        c = Counter()
        for o in self.objects:
            c[(o['classID'], CLASS_NAMES.get(o['classID'], '?'))] += 1
        return c


JP = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF66-\uFF9F]')
KANA = re.compile(r'[\u3040-\u309F\u30A0-\u30FF]')


def text_stats(textassets):
    """统计剧本标记与日文字符量。标记形如 <xxx>。"""
    tag_re = re.compile(r'<[^<>\n]{0,32}>')
    total_bytes = 0
    total_chars = 0
    jp_chars = 0
    kana_chars = 0
    tag_chars = 0
    lines = 0
    for t in textassets:
        if 'script' not in t:
            continue
        s = t['script'].decode('utf-8', 'replace')
        total_bytes += len(t['script'])
        total_chars += len(s)
        for m in tag_re.finditer(s):
            tag_chars += len(m.group(0))
        stripped = tag_re.sub('', s)
        lines += stripped.count('\n')
        for ch in stripped:
            if JP.match(ch):
                jp_chars += 1
                if KANA.match(ch):
                    kana_chars += 1
    return dict(count=len(textassets), total_bytes=total_bytes, total_chars=total_chars,
                jp_chars=jp_chars, kana_chars=kana_chars, tag_chars=tag_chars, lines=lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--info', action='store_true')
    ap.add_argument('--types', action='store_true')
    ap.add_argument('--textassets', action='store_true')
    ap.add_argument('--stats', action='store_true')
    ap.add_argument('--dump-texts', default=None)
    ap.add_argument('--find-name', default=None)
    ap.add_argument('--json', default=None)
    ap.add_argument('--show', type=int, default=0, help='打印前 N 个 TextAsset 内容片段')
    a = ap.parse_args()
    f = UnityFile(a.path, verbose=True)
    if a.info or not any([a.types, a.textassets, a.find_name, a.dump_texts]):
        print(f'[TYPES] {len(f.types)} 个类型')
    if a.types:
        for i, t in enumerate(f.types):
            cnt = sum(1 for o in f.objects if o['typeID'] == i)
            print(f'  [{i:>3}] classID={t["classID"]:>4} {CLASS_NAMES.get(t["classID"],"?"):<16} stripped={t.get("isStripped")} objs={cnt}')
    if a.textassets or a.stats or a.dump_texts or a.show or a.find_name:
        tas = f.textassets()
        errs = [t for t in tas if 'script' not in t]
        print(f'[TEXT] TextAsset 对象数={len(tas)} 解析失败={len(errs)}')
        if a.stats:
            st = text_stats(tas)
            print(f'[STATS] {st}')
        if a.show:
            for t in tas[:a.show]:
                s = t['script'].decode('utf-8', 'replace')
                print(f'--- {t["name"]} (objSize={t["obj"]["byteSize"]} scriptLen={t["script_len"]} off={t["script_off"]}) ---')
                print(s[:600])
        if a.find_name:
            for t in tas:
                if t.get('name') == a.find_name:
                    s = t['script'].decode('utf-8', 'replace')
                    print(f'=== {t["name"]} scriptLen={t["script_len"]} off={t["script_off"]} ===')
                    print(s[:2000])
        if a.dump_texts:
            os.makedirs(a.dump_texts, exist_ok=True)
            with open(os.path.join(a.dump_texts, 'index.json'), 'w', encoding='utf-8') as jf:
                json.dump([{'name': t.get('name'), 'len': t['script_len'], 'off': t['script_off'],
                            'lenFieldOff': t['script_len_field_off'], 'objStart': t['obj']['byteStart'],
                            'objSize': t['obj']['byteSize']} for t in tas], jf, ensure_ascii=False, indent=1)
            for t in tas:
                if 'script' in t:
                    safe = re.sub(r'[^\w.\-]', '_', t['name'])[:80]
                    with open(os.path.join(a.dump_texts, f'{safe}__{t["obj"]["pathID"]}.txt'), 'wb') as fh:
                        fh.write(t['script'])
            print(f'[DUMP] -> {a.dump_texts}')
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as jf:
            json.dump(text_stats(f.textassets()), jf, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
