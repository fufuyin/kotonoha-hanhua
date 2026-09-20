#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 untranslated_all.csv 里的「设计期占位样本」过滤掉，只留下可能是真实可见文本的条目。

占位样本特征：去掉 <i></i> 与换行后，字符全部来自经典假名样张集合
  {あ い う え お か き く け こ さ し す せ そ た ち つ て と}
真实文本特征：含汉字，或含上述集合之外的假名。

输出：_hanhua/out/untranslated_real.csv + 控制台清单
"""
import csv
import io
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SRC = os.path.join(ROOT, "_hanhua", "out", "untranslated_all.csv")
OUT = os.path.join(ROOT, "_hanhua", "out", "untranslated_real.csv")

SAMPLE_CHARS = set("あいうえおかきくけこさしすせそたちつてと")
TAG = re.compile(r"</?[a-zA-Z][^>]*>")


def is_sample(text):
    t = TAG.sub("", text).replace("\n", "").replace("\r", "").replace("\u3000", "").strip()
    if not t:
        return True
    return all(c in SAMPLE_CHARS for c in t)


def main():
    sys.stdout.reconfigure(errors="backslashreplace")
    rows = list(csv.DictReader(io.open(SRC, encoding="utf-8")))
    real = [r for r in rows if not is_sample(r["text"])]
    print("总计 %d 条，其中设计期样张 %d 条，可疑真实文本 %d 条"
          % (len(rows), len(rows) - len(real), len(real)))
    with io.open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(real)
    print("清单 -> " + OUT)
    for r in real:
        body = r["text"].replace("\n", "\\n")
        if len(body) > 150:
            body = body[:150] + "…"
        print("  %s cls=%s %s @%s L=%s\n     %s"
              % (r["file"], r["cls"], r["pathID"], r["strOff"], r["length"],
                 body.encode("ascii", "backslashreplace").decode()))


if __name__ == "__main__":
    main()
