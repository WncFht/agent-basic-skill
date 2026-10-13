# test_zhihu_tardis.py — zhihu-tardis 回归。Run:
#   TMPDIR=$HOME/.cache/lgc-tmp uv run --with pytest pytest skills/link-get/tests -x -q
# Offline：curl/uv 走 PATH stub；LGC_OFF=1 全缓存 no-op。temp 落在 ~/.cache。

import os
import shutil
import subprocess
import tempfile

import pytest

TARDIS = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "connectors", "zhihu-tardis"
)
TMPBASE = os.path.expanduser("~/.cache")

CURL_STUB = """#!/bin/bash
# -w "%{http_code}" 的 stdout 由 TARDIS_STUB_CODE 控制；-o 不落文件
printf '%s' "${TARDIS_STUB_CODE:-302}"
exit 0
"""

UV_STUB = """#!/bin/bash
exit 0
"""


@pytest.fixture
def env():
    home = tempfile.mkdtemp(prefix="tardis-test-", dir=TMPBASE)
    stub = os.path.join(home, "bin")
    out = os.path.join(home, "out")
    os.makedirs(stub)
    os.makedirs(out)
    e = dict(os.environ)
    e["PATH"] = stub + os.pathsep + e["PATH"]
    e["LGC_OFF"] = "1"
    yield e, home, stub, out
    shutil.rmtree(home, ignore_errors=True)


def put_stub(stubdir, name, body):
    p = os.path.join(stubdir, name)
    with open(p, "w") as f:
        f.write(body)
    os.chmod(p, 0o755)
    return p


def run_tardis(e, url, out):
    return subprocess.run(
        ["bash", TARDIS, url, "-o", out],
        env=e,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://zhuanlan.zhihu.com/p/notanumber",
        "https://zhuanlan.zhihu.com/p/",
        "https://www.zhihu.com/question/555/answer/xyz",  # 数字在 question/ 段不算
    ],
)
def test_nonnumeric_id_exit2(env, url):
    """非数字 id：grep 管道在 pipefail 下曾 exit1 死卫；应为 usage exit2。"""
    e, _home, _stub, out = env
    r = run_tardis(e, url, out)
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert "解不出" in r.stderr


def test_numeric_id_passes_guard(env):
    """对照组：数字 id 过卫 → 走到抓取（stub curl 302 → tardis-miss exit3）。"""
    e, _home, stub, out = env
    put_stub(stub, "curl", CURL_STUB)
    put_stub(stub, "uv", UV_STUB)  # dep 门：command -v uv 须在
    e["TARDIS_STUB_CODE"] = "302"
    r = run_tardis(e, "https://zhuanlan.zhihu.com/p/123456", out)
    assert r.returncode == 3, (r.returncode, r.stderr)


# --- _lgc.sh single-source（搬家后 canon 与 connectors 同目录；旧位残留只许软链）---

CANON = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "connectors", "_lgc.sh"
)
# 旧 skill 位过渡残留：删除前只允许软链回指 canon，实体副本即漂移
ZH_LGC = os.path.join(
    os.path.dirname(__file__), "..", "..", "zhihu", "scripts", "_lgc.sh"
)


def test_lgc_sh_single_source():
    """canon 在 connectors/ 与 zhihu-tardis 同目录；旧位残留若非缺席须软链回指。"""
    sib = os.path.join(os.path.dirname(TARDIS), "_lgc.sh")
    assert os.path.isfile(sib)
    assert os.path.realpath(sib) == os.path.realpath(CANON)
    if os.path.lexists(ZH_LGC):
        assert os.path.islink(ZH_LGC), "旧位 _lgc.sh 须为软链而非实体副本"
        assert os.path.realpath(ZH_LGC) == os.path.realpath(CANON)


def test_tardis_no_inline_block():
    """zhihu-tardis 不再内嵌 PROBE-BLOCK；改为 source 同目录 _lgc.sh。"""
    with open(TARDIS, encoding="utf-8") as f:
        src = f.read()
    assert "LGC-PROBE-BLOCK" not in src
    assert '_lgc.sh"' in src  # . "$SCRIPT_DIR/_lgc.sh"


def test_tardis_stub_fallback_without_lgc_sh(env):
    """_lgc.sh 缺席 → stub 降级而非死：拷贝 tardis 独身进临时目录，
    z_probe stub miss → 照常走抓取（stub curl 302 → exit3）。"""
    e, home, stub, out = env
    solo = os.path.join(home, "solo")
    os.makedirs(solo)
    shutil.copy(TARDIS, os.path.join(solo, "zhihu-tardis"))  # 无 _lgc.sh 邻居
    put_stub(stub, "curl", CURL_STUB)
    put_stub(stub, "uv", UV_STUB)
    e["TARDIS_STUB_CODE"] = "302"
    e.pop("LGC_OFF", None)  # 走真 stub 路径而非 env 短路
    r = subprocess.run(
        [
            "bash",
            os.path.join(solo, "zhihu-tardis"),
            "https://zhuanlan.zhihu.com/p/123456",
            "-o",
            out,
        ],
        env=e,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 3, (r.returncode, r.stderr)


def test_tardis_partial_lgc_sh_still_stubs(env):
    """半截 _lgc.sh（截断写/冲突标/坏盘）：z_probe 在但 z_lane 缺席——
    旧卫只查 z_probe 会放行半截函数集 → z_lane rc127 死；
    新卫全集任缺 → 清残余装整组 stub → 照常降级（verify 实锤）。"""
    e, home, stub, out = env
    solo = os.path.join(home, "solo")
    os.makedirs(solo)
    shutil.copy(TARDIS, os.path.join(solo, "zhihu-tardis"))
    with open(os.path.join(solo, "_lgc.sh"), "w") as f:
        f.write(
            "# 模拟半截 source：只有 z_probe，其余函数缺席\n"
            'z_probe() { ZHIT=miss; ZRC=1; ZNEG=""; ZPATHS=""; return 0; }\n'
        )
    put_stub(stub, "curl", CURL_STUB)
    put_stub(stub, "uv", UV_STUB)
    e["TARDIS_STUB_CODE"] = "302"
    e.pop("LGC_OFF", None)
    r = subprocess.run(
        [
            "bash",
            os.path.join(solo, "zhihu-tardis"),
            "https://zhuanlan.zhihu.com/p/123456",
            "-o",
            out,
        ],
        env=e,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 3, (r.returncode, r.stderr)
    assert "command not found" not in r.stderr
