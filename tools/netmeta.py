#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
正确的 .NET 程序集字符串提取器（解析 PE -> CLI Header -> Metadata -> #US / #Strings 堆）。
不依赖第三方库。
用法:
  python netmeta.py <assembly.dll> [--heap us|strings|both] [--dump out.txt] [--filter JP|ALL] [--sample N] [--json out.json]
"""
import struct, sys, argparse, os, re, json

class PE:
    def __init__(self, path):
        self.buf = open(path, 'rb').read()
        b = self.buf
        if b[:2] != b'MZ':
            raise ValueError('not a PE file')
        e_lfanew = struct.unpack_from('<I', b, 0x3C)[0]
        if b[e_lfanew:e_lfanew+4] != b'PE\0\0':
            raise ValueError('no PE signature')
        coff = e_lfanew + 4
        (self.machine, self.nsec, _, _, _, self.opt_size, self.chars) = struct.unpack_from('<HHIIIHH', b, coff)
        self.opt = coff + 20
        magic = struct.unpack_from('<H', b, self.opt)[0]
        self.pe32plus = (magic == 0x20B)
        dd = self.opt + (112 if self.pe32plus else 96)
        # data directory 14 = CLI header
        self.cli_rva, self.cli_size = struct.unpack_from('<II', b, dd + 14*8)
        sec = self.opt + self.opt_size
        self.sections = []
        for i in range(self.nsec):
            o = sec + i*40
            name = b[o:o+8].rstrip(b'\0').decode('latin1')
            vsize, va, rawsize, rawptr = struct.unpack_from('<IIII', b, o+8)
            self.sections.append((name, va, vsize, rawptr, rawsize))
        self.rva2off(self.cli_rva)
        self.metadata_fields = self._cli()

    def rva2off(self, rva):
        for name, va, vsize, rawptr, rawsize in self.sections:
            if va <= rva < va + max(vsize, rawsize):
                return rva - va + rawptr
        raise ValueError(f'RVA 0x{rva:x} not mapped')

    def _cli(self):
        o = self.rva2off(self.cli_rva)
        cb, major, minor, md_rva, md_size, flags = struct.unpack_from('<IHHII4s', self.buf, o)
        self.md_rva, self.md_size = md_rva, md_size
        o = self.rva2off(md_rva)
        sig = self.buf[o:o+4]
        if sig != b'BSJB':
            raise ValueError('bad metadata signature')
        ver_len = struct.unpack_from('<I', self.buf, o+12)[0]
        p = o + 16 + ((ver_len + 3) // 4) * 4
        flags, nstreams = struct.unpack_from('<HH', self.buf, p)
        p += 4
        streams = {}
        for _ in range(nstreams):
            soff, ssize = struct.unpack_from('<II', self.buf, p)
            p += 8
            end = self.buf.index(b'\0', p)
            name = self.buf[p:end].decode('latin1')
            p = end + 1
            p = (p + 3) & ~3
            streams[name] = (o + soff, ssize)
        self.streams = streams
        return streams


def read_compressed(buf, off):
    b0 = buf[off]
    if b0 & 0x80 == 0:
        return b0, off + 1
    if b0 & 0xC0 == 0x80:
        return ((b0 & 0x3F) << 8) | buf[off+1], off + 2
    if b0 & 0xE0 == 0xC0:
        return ((b0 & 0x1F) << 24) | (buf[off+1] << 16) | (buf[off+2] << 8) | buf[off+3], off + 4
    raise ValueError(f'bad compressed integer at {off}')


def parse_us(pe):
    """返回 #US 堆中的字符串字面量列表（按物理顺序，含重复）。"""
    off, size = pe.streams['#US']
    buf = pe.buf
    end = off + size
    out = []
    p = off + 1  # 首字节为 0（空项）
    while p < end:
        try:
            length, p2 = read_compressed(buf, p)
        except Exception:
            break
        if length == 0:
            p = p + 1
            continue
        if p2 + length > end:
            break
        data = buf[p2:p2+length]
        # 末字节为字符串种类标记
        try:
            s = data[:-1].decode('utf-16-le', errors='surrogatepass')
        except Exception:
            s = data[:-1].decode('utf-16-le', errors='replace')
        out.append(s)
        p = p2 + length
    return out


def parse_strings(pe):
    off, size = pe.streams['#Strings']
    raw = pe.buf[off:off+size]
    return [s.decode('utf-8', errors='replace') for s in raw.split(b'\0') if s]


JP_RE = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF66-\uFF9F\u3000-\u303F]')
KANA_RE = re.compile(r'[\u3040-\u309F\u30A0-\u30FF]')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--heap', default='us', choices=['us', 'strings', 'both'])
    ap.add_argument('--filter', default='JP', choices=['JP', 'ALL', 'KANA'])
    ap.add_argument('--dump', default=None)
    ap.add_argument('--json', default=None)
    ap.add_argument('--sample', type=int, default=0)
    ap.add_argument('--minlen', type=int, default=1)
    a = ap.parse_args()
    pe = PE(a.path)
    print(f'[PE] sections={len(pe.sections)} streams={list(pe.streams.keys())}')
    items = []
    if a.heap in ('us', 'both'):
        items += [('US', s) for s in parse_us(pe)]
    if a.heap in ('strings', 'both'):
        items += [('STR', s) for s in parse_strings(pe)]
    print(f'[raw] total strings = {len(items)} (us/strings)')
    def keep(s):
        if len(s) < a.minlen:
            return False
        if a.filter == 'ALL':
            return True
        if a.filter == 'JP':
            return bool(JP_RE.search(s))
        return bool(KANA_RE.search(s))
    sel = [(src, s) for src, s in items if keep(s)]
    uniqs = sorted(set(s for _, s in sel), key=lambda s: (-len(s), s))
    print(f'[sel] filter={a.filter} hits={len(sel)} unique={len(uniqs)} chars={sum(len(s) for s in uniqs)}')
    if a.sample:
        for i, s in enumerate(uniqs[:a.sample]):
            print(f'{i:>4} {s!r}')
    if a.dump:
        os.makedirs(os.path.dirname(os.path.abspath(a.dump)), exist_ok=True)
        with open(a.dump, 'w', encoding='utf-8') as f:
            for s in uniqs:
                f.write(s + '\n')
        print('dump ->', a.dump)
    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump({'path': a.path, 'selected_unique': uniqs,
                       'all_us_count': len([1 for src, _ in items if src == 'US'])}, f, ensure_ascii=False, indent=1)
        print('json ->', a.json)

if __name__ == '__main__':
    main()
