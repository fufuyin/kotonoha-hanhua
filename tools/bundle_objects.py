#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 raw bundle 抽出的 SerializedFile 里，用「自验证扫描」定位对象表并列出对象。

为什么不用 unityfile.py：那是按「玩家 .assets（无类型树）」写的，bundle 的元数据段
（类型树/字符串缓冲）布局不同，直接解析会越界。这里只依赖两个已验证的事实：
  * 头 16 字节：metadataSize/fileSize/version/dataOffset（大端）
  * 对象条目 24 字节：i64 pathID, u32 byteStart, u32 byteSize, i32 typeID
然后用**强不变式**判定候选表位置：对象必须恰好铺满数据段
  min(byteStart)==0 且 max(byteStart+byteSize)==fileSize-dataOffset
"""
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bundle_extract import lz4_block


def extract_data(bundle):
    d = open(bundle, "rb").read()
    p = 8 + 4
    for _ in range(2):
        p = d.index(b"\x00", p) + 1
    size, cbis, ubis, flags = struct.unpack_from(">qIII", d, p); p += 20
    bi = lz4_block(d[p:p + cbis], ubis); p += cbis
    q = 16
    cnt = struct.unpack_from(">i", bi, q)[0]; q += 4
    data = bytearray()
    for _ in range(cnt):
        u, c, f = struct.unpack_from(">IIH", bi, q); q += 10
        assert (f & 0x3F) == 0
        data += d[p:p + u]; p += u
    return bytes(data)


def try_table(buf, t, data_len):
    try:
        n = struct.unpack_from("<i", buf, t)[0]      # 元数据段是**小端**（头才是大端）
    except Exception:
        return None
    if not (1 <= n <= 20000):
        return None
    pos = (t + 4 + 3) & ~3
    for _ in range(t % 4):
        pos += 0
    objs = []
    p = pos
    for _ in range(n):
        if p + 20 > len(buf):
            return None
        pid, bs, sz, tid = struct.unpack_from("<qIIi", buf, p)
        p += 20                                  # v19 条目 = 8+4+4+4 = 20 字节
        if bs > data_len or bs + sz > data_len:
            return None
        if tid < 0 or tid > 4096:
            return None
        objs.append((pid, bs, sz, tid))
    if not objs:
        return None
    hi = max(o[1] + o[2] for o in objs)
    # 放宽到「全部落在数据段内、且覆盖大部分数据段」，不再要求首对象从 0 开始
    if hi > data_len or hi < data_len * 0.5:
        return None
    if len(set(o[0] for o in objs)) != len(objs):      # pathID 必须唯一
        return None
    return objs, pos, n


def main():
    bundle = sys.argv[1]
    buf = extract_data(bundle)
    ms, fs, ver, do = struct.unpack_from(">IIII", buf, 0)
    print("header: metadataSize=%d fileSize=%d version=%d dataOffset=%d actual=%d" % (ms, fs, ver, do, len(buf)))
    data_len = fs - do
    print("data section: %d bytes (dataOffset..fileSize)" % data_len)

    found = None
    cands = []
    for t in range(20, do, 4):
        r = try_table(buf, t, data_len)
        if r:
            objs2, pos2, n2 = r
            sizes = [o[2] for o in objs2]
            score = 0
            if any(67100000 <= s <= 67130000 for s in sizes):
                score += 2                                     # 8192² Alpha8 图集
            if any(s > 300000 for s in sizes):
                score += 1                                     # 字体资产应达数百 KB
            if 4 <= n2 <= 10:
                score += 1
            cands.append((score, t, pos2, n2, objs2))
    if not cands:
        print("!! 没有候选对象表")
        return 2
    cands.sort(key=lambda c: (-c[0], c[3], c[2]))
    score, t, pos, n, objs = cands[0]
    print("候选表数量=%d，选中: obj_n 字段在 %d, 条目起于 %d, 对象数=%d, 含64MB图集=%s"
          % (len(cands), t, pos, n, score == 1))
    if len(cands) > 1:
        print("  其它候选(前3): " + str([(c[0], c[1], c[3]) for c in cands[1:4]]))
    found = (t, objs, pos, n)
    print("对象表: obj_n 字段在 %d, 条目从 %d 开始, 共 %d 个对象" % (t, pos, n))
    print("  前 3 个: " + str([(hex(o[0]), o[1], o[2], o[3]) for o in objs[:3]]))
    print("  typeID 取值集合: %s" % sorted(set(o[3] for o in objs))[:12])
    print("  payload 最大的 6 个:")
    for (pid, bs, sz, tid) in sorted(objs, key=lambda x: -x[2])[:6]:
        print("     pathID=0x%x typeID=%d size=%d abs=%d" % (pid, tid, sz, do + bs))
    # 按大小识别：图集 = 恰好 8192*8192 = 67108864；字体资产 = 含连续 u32 码位
    atlas = [o for o in objs if o[2] == 8192 * 8192]
    print("  恰为 8192x8192 Alpha8 的 payload: %s" % [(hex(o[0]), o[2]) for o in atlas])
    cand = [o for o in objs if 200000 < o[2] < 2000000]
    print("  200KB~2MB 的候选(字体资产?): %s" % [(hex(o[0]), o[2], o[3]) for o in cand])
    for (pid, bs, sz, tid) in cand:
        blob = buf[do + bs: do + bs + min(sz, 4000)]
        # TMP 字符表里存 u32 码位，找几个常见汉字码位的出现次数做旁证
        hits = 0
        for cp in (0x4E00, 0x5B57, 0x7684, 0x4E2D):
            hits += blob.count(struct.pack(">I", cp)) + blob.count(struct.pack("<I", cp))
        print("     pathID=0x%x 前4000字节里常见汉字码位命中=%d" % (pid, hits))
    return 0


if __name__ == "__main__":
    sys.exit(main())
