#!/usr/bin/env python3
"""canvas-rest lane — canvas 枚举 REST 子命令 → {type:data} 终态。

identity.params.enum ∈ {lectures,courses,files,announcements,assignments}，
缺席默认 lectures——kind_by_url 把课程根 URL 判进 enum 时不带 enum 注入，
'link-get 97882'/裸课程页 URL 的落地语义即"列讲次"（直连 canvas-get <课>
无旗标的平价）。courses → --list-courses；其余把 identity.raw 作课程位置参
（canvas-get 自吃课程页 URL / 裸 ID，亦收 params.course 显式覆盖）。
payload = connector stdout 逐字——消费侧与直连 canvas-get 平价。
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib

FLAGS = {
    "lectures": [],  # 列讲次无旗标——裸 canvas-get <course> 即此臂
    "courses": ["--list-courses"],
    "files": ["--files"],
    "announcements": ["--announcements"],
    "assignments": ["--assignments"],
}
# 与枚举语义兼容的可透传旗标（--download 不经此道——签名链契约直连）
PASS_THROUGH = {"refresh": "--refresh", "no_cache": "--no-cache"}

# enum 缺席时的布尔回波派生表（裸课程 ID/-p 直达不经分发层注 enum 时兜底）；
# 与 link-get 旗标→enum 注入同序，末中者赢；mint 命中应被 routes 提前拦走，
# 漏到这里一律 notcovered 诚实报错（FLAGS 无 mint 臂）
_DERIVE = (
    ("list_courses", "courses"),
    ("files", "files"),
    ("announcements", "announcements"),
    ("assignments", "assignments"),
    ("mint", "mint"),
)


def _truthy(v):
    if isinstance(v, bool):
        return v
    return isinstance(v, str) and v.lower() in ("1", "true", "yes", "on")


def main():
    req = _lib.read_req()
    ident = req.get("identity") or {}
    ctx = req.get("ctx") or {}
    params = ident.get("params") or {}
    enum = params.get("enum") or ""
    if not enum:
        for k, v in _DERIVE:
            if _truthy(params.get(k)):
                enum = v
        enum = enum or "lectures"
    if enum not in FLAGS:
        _lib.die("notcovered", f"enum={enum!r} ∉ {sorted(FLAGS)}")

    argv = [_lib.canvas_get_bin()]
    if enum == "courses":
        argv += FLAGS[enum]
    else:
        course = ident.get("raw") or params.get("course")
        # 无课程参的落地（壳对裸枚举旗标回填的是站点根 URL）必须诚实拒——
        # 拿根 URL 当课程喂 connector 只会 rc0 打印空表假成功
        if not course or not re.search(r"/courses/[0-9]+|^[0-9]{4,6}$", str(course)):
            _lib.die(
                "notcovered",
                f"enum={enum} 需要课程 URL/ID（--list-courses 免课程）",
            )
        argv += [str(course), *FLAGS[enum]]
    for k, flag in PASS_THROUGH.items():
        if params.get(k):
            argv.append(flag)
    if params.get("cache_ttl"):
        argv += ["--cache-ttl", str(params["cache_ttl"])]

    p = _lib.run_canvas_get(argv, ctx)
    _lib.finish(p)  # 非 0 → 终态 error；rc0 续行
    _lib.emit({"type": "data", "payload": p.stdout or ""})


if __name__ == "__main__":
    main()
