#!/usr/bin/env python3
"""转写稿工具：srt 压缩为 `MM:SS 文本` 时间戳稿 + 按时段切片。

长视频分段精读的标准件——先 srt2ts 出压缩稿，再 slice 给每个分段
精读 subagent 一段 seg_N.txt，避免每个子代理自己重造 awk 截取。

用法：
  python3 transcript.py srt2ts audio.srt --out transcript_ts.txt
  python3 transcript.py slice transcript_ts.txt --start 11:00 --end 23:00 \
      --out seg_2.txt          # 边界含重叠：>=start-15s 且 <end+15s 的行带出
  python3 transcript.py slice transcript_ts.txt --start 11:00 --end 23:00 \
      --overlap 0             # 严格边界

时间戳支持 SS / MM:SS / HH:MM:SS。输入 srt2ts 之外的文件须为
`MM:SS 文本`（或 HH:MM:SS）行格式——其它行原样透传。
"""

import argparse
import re
import sys
from pathlib import Path

CUE = re.compile(r"(\d+):(\d\d):(\d\d)[,.](\d+)\s*-->\s*(\d+):(\d\d):(\d\d)[,.](\d+)")
TS_LINE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d\d)\s+(.*)$")


def to_s(h, m, s):
    return h * 3600 + m * 60 + s


def fmt(s):
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def parse_t(s):
    parts = [int(p) for p in s.split(":")]
    return sum(p * 60**i for i, p in enumerate(reversed(parts)))


def cmd_srt2ts(a):
    text = Path(a.srt).read_text(encoding="utf-8")
    out = Path(a.out) if a.out else Path(a.srt).with_suffix(".ts.txt")
    lines = []
    for m in CUE.finditer(text):
        t = to_s(int(m[1]), int(m[2]), int(m[3]))
        # cue 文本 = match 之后到下一个序号/空行块
        seg = text[m.end() :]
        body = re.split(r"\n\s*\n|\n\d+\s*\n\d\d:", seg, maxsplit=1)[0]
        body = " ".join(body.split())
        if body:
            # >=1h 用 H:MM:SS——MM:SS 在 100 分钟后变三位数，TS_LINE 会失配
            stamp = f"{t // 60:02d}:{t % 60:02d}" if t < 3600 else fmt(t)
            lines.append(f"{stamp} {body}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(lines)} 行 -> {out}")


def cmd_slice(a):
    path = Path(a.file)
    t0, t1 = parse_t(a.start), parse_t(a.end)
    lo, hi = t0 - a.overlap, t1 + a.overlap
    kept, total = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        m = TS_LINE.match(line)
        if not m:
            continue
        total += 1
        t = to_s(int(m[1] or 0), int(m[2]), int(m[3]))
        if lo <= t < hi:
            kept.append(line)
    if not kept:
        sys.exit(
            f"{a.start}--{a.end} 区间无内容（共 {total} 行带时间戳）；"
            "检查时段边界是否越界"
        )
    body = "\n".join(kept) + "\n"
    if a.out:
        Path(a.out).write_text(body, encoding="utf-8")
        print(
            f"{fmt(t0)}--{fmt(t1)} (+/-{a.overlap}s): {len(kept)}/{total} 行 -> {a.out}"
        )
    else:
        sys.stdout.write(body)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("srt2ts", help="srt -> `MM:SS 文本` 时间戳稿")
    p.add_argument("srt")
    p.add_argument("--out", default=None, help="缺省 <name>.ts.txt")
    p.set_defaults(f=cmd_srt2ts)

    p = sub.add_parser("slice", help="按时段切片")
    p.add_argument("file", help="transcript_ts.txt 之类 `MM:SS 文本` 文件")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--overlap", type=int, default=15, help="边界重叠秒数（默认 15）")
    p.add_argument("--out", default=None, help="缺省写 stdout")
    p.set_defaults(f=cmd_slice)

    args = ap.parse_args()
    args.f(args)


if __name__ == "__main__":
    main()
