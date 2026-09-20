#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用「原地等长字符串替换」工具（Unity SerializedFile 安全编辑）。

原理：Unity 字符串 = [i32 字节长度][UTF-8 内容][补齐到 4 字节]。
      只要新内容的 UTF-8 字节数 <= 原长度，就能原地覆盖并保持后面所有字段偏移不变。
      差额用 U+3000（全角空格，3 字节）或换行补齐到**完全相同**的字节长度。

安全机制：
  * 默认 dry-run，只有 --apply 才写盘
  * 写盘前自动备份 <file>.before_<tag>
  * 写盘后重新解析，核对「对象数 / 文件大小 / 字符串长度」三项不变
  * 用 pathID 精确指定对象，避免误伤

用法:
  python patch_string_inplace.py <assets 文件> --pathid 0x89a0 --old "<i>を手に入れた</i>" --new "<i>已获得</i>" --tag item
"""
import argparse
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfile import UnityFile


def unity_strings_at(raw):
    """[(content_off_in_raw, L, text)]"""
    out = []
    i = 0
    n = len(raw)
    while i + 4 <= n:
        L = struct.unpack_from("<i", raw, i)[0]
        if 1 <= L <= 4000 and i + 4 + L <= n:
            bs = raw[i + 4:i + 4 + L]
            if b"\x00" not in bs:
                try:
                    s = bs.decode("utf-8")
                except UnicodeDecodeError:
                    i += 1
                    continue
                out.append((i + 4, L, s))
                i += 4 + L
                i = (i + 3) & ~3
                continue
        i += 1
    return out


def pad_to(text, target_len):
    """把 text 用 U+3000 补齐到 target_len 字节；补不齐返回 None。"""
    b = text.encode("utf-8")
    if len(b) > target_len:
        return None
    diff = target_len - len(b)
    if diff % 3 == 0:
        return text + "\u3000" * (diff // 3)
    if diff % 3 == 1:
        return text + "\n" + "\u3000" * ((diff - 1) // 3)
    if diff == 2:
        return text + "\n\n"
    return text + "\n" * (diff % 2) + "\u3000" * ((diff - diff % 2) // 3) if diff % 3 == 2 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--pathid", required=True, help="如 0x89a0")
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--tag", default="patch")
    ap.add_argument("--substr", action="store_true",
                    help="old/new are SUBSTRINGS inside a longer string; the string keeps its byte length (tail padded with U+3000)")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(errors="backslashreplace")

    pid = int(a.pathid, 16)
    uf = UnityFile(a.path, verbose=False)
    target = [o for o in uf.objects if o["pathID"] == pid]
    if not target:
        print("找不到 pathID=0x%x" % pid)
        return 2
    o = target[0]
    raw = uf.buf[o["abs"]:o["abs"] + o["byteSize"]]

    if a.substr:
        hits = [(off, L, s) for (off, L, s) in unity_strings_at(raw) if a.old in s]
    else:
        hits = [(off, L, s) for (off, L, s) in unity_strings_at(raw) if s == a.old]
    if not hits:
        print("该对象里找不到匹配；对象内的字符串有：")
        for off, L, s in unity_strings_at(raw)[:10]:
            print("   @%d L=%d %r" % (off, L, s))
        return 2

    plans = []
    for off, L, s in hits:
        if a.substr:
            new = s.replace(a.old, a.new)
            if len(new.encode("utf-8")) > L:
                print("替换后过长：L=%d 需 %d 字节" % (L, len(new.encode("utf-8"))))
                return 2
            new = pad_to(new, L)
            if new is None:
                print("补齐失败 L=%d" % L)
                return 2
        else:
            new = pad_to(a.new, L)
            if new is None:
                print("新内容太长：L=%d，new=%d 字节" % (L, len(a.new.encode("utf-8"))))
                return 2
        plans.append((o["abs"] + off, L, s, new))

    print("命中 %d 处（对象 0x%x, cls=%s, size=%d）" % (len(plans), pid, o["classID"], o["byteSize"]))
    for abs_off, L, s, new in plans:
        print("  @%d L=%d" % (abs_off, L))
        print("     原: %r" % s)
        print("     新: %r  (%d 字节)" % (new, len(new.encode("utf-8"))))
    if not a.apply:
        print("\n[dry-run] 未写盘；确认无误后加 --apply")
        return 0

    backup = a.path + ".before_" + a.tag
    if not os.path.exists(backup):
        shutil.copyfile(a.path, backup)
        print("备份 -> " + backup)
    else:
        print("备份已存在，保留原备份: " + backup)

    size_before = os.path.getsize(a.path)
    buf = bytearray(open(a.path, "rb").read())
    for abs_off, L, s, new in plans:
        buf[abs_off:abs_off + L] = new.encode("utf-8")
    open(a.path, "wb").write(bytes(buf))

    # 验证
    uf2 = UnityFile(a.path, verbose=False)
    size_after = os.path.getsize(a.path)
    print("[verify] 对象数 %d -> %d ; 文件大小 %d -> %d ; 大小不变=%s"
          % (len(uf.objects), len(uf2.objects), size_before, size_after, size_before == size_after))
    obj2 = [x for x in uf2.objects if x["pathID"] == pid][0]
    raw2 = uf2.buf[obj2["abs"]:obj2["abs"] + obj2["byteSize"]]
    now = [s for (off, L, s) in unity_strings_at(raw2) if a.new in s]
    print("[verify] 目标对象里已可见新文本 %d 处" % len(now))
    for s in now[:3]:
        print("     %r" % s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
