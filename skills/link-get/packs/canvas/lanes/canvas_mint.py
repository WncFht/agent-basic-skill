#!/usr/bin/env python3
"""canvas-mint meta-lane — canvas-get --mint 铸 LTI cred value 键。

writes_cred=canvas-skill（pack.toml 声明）：jwt:<tok8>:<cid>/tecl:<tok8>:<cid>
由 canvas-get 经 lgc vput 落 cred store——lane 本身不写 artifact_dir 之外。
{type:data} 终态：payload = 铸键证据行（键名+tecl 值，jwt 永不出界）。
identity.raw 作课程位置参（URL/裸 ID 皆可，params.course 显式覆盖）。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib


def main():
    req = _lib.read_req()
    ident = req.get("identity") or {}
    ctx = req.get("ctx") or {}
    params = ident.get("params") or {}
    course = ident.get("raw") or params.get("course")
    if not course:
        _lib.die("notcovered", "mint 需要课程 URL/ID（raw/course 均空）")

    argv = [_lib.canvas_get_bin(), str(course), "--mint"]
    p = _lib.run_canvas_get(argv, ctx)
    _lib.finish(p)
    _lib.emit({"type": "data", "payload": p.stdout or ""})


if __name__ == "__main__":
    main()
