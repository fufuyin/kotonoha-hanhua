#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断：枚举 payload 中所有 == 8192*8192 的 i32，打印其后续 96 字节，用于判断哪个才是 m_ImageData 长度字段。

用法: python probe_tex_header.py <file.assets|serialized> [more...]
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile

PIX = 8192 * 8192


def main():
    for path in sys.argv[1:]:
        f = UnityFile(path, verbose=False)
        print(f'=== {os.path.basename(path)} ===')
        for o in f.objects:
            if o['classID'] != 28 or o['byteSize'] < 1024 * 1024:
                continue
            p = f.buf[o['abs']:o['abs'] + o['byteSize']]
            print(f'--- pathID={o["pathID"] & 0xFFFFFFFFFFFFFFFF:016x} size={o["byteSize"]} ---')
            pat = struct.pack('<i', PIX)
            s, cands = 0, []
            while True:
                i = p.find(pat, s)
                if i < 0:
                    break
                cands.append(i)
                s = i + 1
            for i in cands:
                t = i + 4 + PIX
                tail = p[t:] if t <= len(p) else b''
                info = ''
                if len(tail) >= 16:
                    off, size, plen = struct.unpack_from('<qii', tail, 0)
                    info = f'[i64off={off} i32size={size} i32plen={plen}]'
                print(f'    cand@{i} tail_len={t <= len(p) and len(tail) or -1} {info}')
                if len(tail):
                    print(f'        tail[0:48]={tail[:48].hex(" ")}')
                    print(f'        tail ascii ={"".join(chr(c) if 32 <= c < 127 else "." for c in tail[:48])}')
            # 该 texture 的 m_StreamData 相关尾部（取最后一个可打印串）
            print(f'    payload[-64:]={p[-64:].hex(" ")}')
            print(f'    ascii        ={"".join(chr(c) if 32 <= c < 127 else "." for c in p[-64:])}')
            # 黄金像素标定：在 payload 里搜 twobake_atlas.bin 的开头
            import os as _os
            g = r'F:\Application\Unity\twobake_atlas.bin'
            if _os.path.exists(g) and _os.path.getsize(g) == PIX:
                with open(g, 'rb') as fh:
                    needle = fh.read(64)
                k = p.find(needle)
                print(f'    [golden] twobake_atlas.bin 起始 64 字节在 payload+{k} 出现')
                if k >= 0:
                    tailg = p[k + PIX:]
                    print(f'    [golden] 像素尾部长度={len(tailg)} 内容={tailg.hex(" ")}')
                    print(f'    [golden] 像素前 8 字节={p[k - 8:k].hex(" ")}')


if __name__ == '__main__':
    main()
