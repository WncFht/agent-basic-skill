#!/usr/bin/env python3
"""test_render.py — render.py 分发 + render_mpl 统一审计输出契约的自测试。

覆盖：
- dispatch：.tex/.frag → render_tex，.json → render_mpl（后端用 stub 捕获
  argv，不需要 matplotlib/xelatex）
- 旗标映射：--no-audit→--no-check、.frag 隐含 --frag、--no-coverage/--no-readback/
  --overlay 透传、tex 专有旗标喂 .json 报 2、未知扩展名报 2、退出码透传、
  sys.argv 还原
- mpl 面（有 matplotlib 才跑）：真实 spec 走 render_mpl.main / render.main，
  断言统一行格式（'ERR <rule>: msg'/'warn <rule>: msg'/'warn lint:<name>: msg'）
  与退出码契约（warn 不 fail、error 才 fail、spec 错误 2、--no-audit 全跳）

运行：python3 scripts/test_render.py          # 仅 stdlib 部分
      uv run --no-project --with matplotlib --with numpy python scripts/test_render.py
"""

import contextlib
import io
import json
import sys
import tempfile
import types
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import render  # noqa: E402  # 被测对象：统一入口（后端惰性 import）
from testkit import FAILS, check  # noqa: E402  # sys.path 引导之后的本地导入

# ---------------------------------------------------------------- dispatch 桩


def _stub(modname, rc=0):
    """sys.modules 预置假后端：main() 捕获 sys.argv 并返回 rc。"""
    cap = {}

    def fake_main():
        cap["prog"], cap["argv"] = sys.argv[0], sys.argv[1:]
        return rc

    sys.modules[modname] = types.SimpleNamespace(main=fake_main)
    return cap


def _unstub(*names):
    for n in names:
        sys.modules.pop(n, None)


def _run(argv):
    """跑 render.main(argv)，捕获 stdout/stderr 与退出码。"""
    out, err = io.StringIO(), io.StringIO()
    argv_before = list(sys.argv)
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = render.main(argv)
    return rc, out.getvalue(), err.getvalue(), sys.argv == argv_before


def dispatch():
    cap = _stub("render_tex", rc=7)
    rc, out, err, restored = _run(["fig.tex"])
    check(
        "tex dispatch + rc passthrough",
        rc == 7
        and cap["prog"] == "render_tex.py"
        and cap["argv"] == ["fig.tex"]
        and restored,
        f"rc={rc} cap={cap} restored={restored}",
    )

    cap = _stub("render_tex")
    rc, *_ = _run(
        [
            "f.tex",
            "--frag",
            "--dpi",
            "150",
            "--outdir",
            "imgs",
            "--no-svg",
            "--no-png",
            "--no-audit",
        ]
    )
    check(
        "tex flag mapping",
        rc == 0
        and cap["argv"]
        == [
            "f.tex",
            "--frag",
            "--dpi",
            "150",
            "--outdir",
            "imgs",
            "--no-check",
            "--no-svg",
            "--no-png",
        ],
        f"argv={cap['argv']}",
    )

    cap = _stub("render_tex")
    _run(["f.frag"])
    check(
        "frag suffix implies --frag", cap["argv"] == ["f.frag", "--frag"], cap["argv"]
    )

    cap = _stub("render_tex")
    _run(["f.tex", "--no-check"])  # --no-check 是 --no-audit 的别名
    check("no-check alias", "--no-check" in cap["argv"], cap["argv"])

    cap = _stub("render_mpl", rc=0)
    rc, *_ = _run(["s.spec.json", "--no-audit", "--dpi", "200", "--outdir", "o"])
    check(
        "json dispatch",
        cap["prog"] == "render_mpl.py"
        and cap["argv"]
        == ["s.spec.json", "--dpi", "200", "--outdir", "o", "--no-audit"],
        f"cap={cap}",
    )

    for bad in ("--frag", "--no-svg", "--no-png", "--no-coverage"):
        cap = _stub("render_mpl")
        rc, _, err, _ = _run(["s.json", bad])
        check(
            f"tex-only flag {bad} rejected on json",
            rc == 2 and bad in err and "argv" not in cap,
            f"rc={rc} err={err.strip()}",
        )
        _unstub("render_mpl")

    cap = _stub("render_tex")
    _run(["f.tex", "--no-coverage", "--no-readback", "--overlay"])
    check(
        "tex audit-trio flags",
        cap["argv"] == ["f.tex", "--no-coverage", "--no-readback", "--overlay"],
        f"argv={cap['argv']}",
    )

    cap = _stub("render_mpl")
    _run(["s.json", "--no-readback", "--overlay"])
    check(
        "json readback/overlay passthrough",
        cap["argv"] == ["s.json", "--no-readback", "--overlay"],
        f"argv={cap['argv']}",
    )

    rc, _, err, _ = _run(["x.png"])
    check("unknown ext", rc == 2 and "cannot dispatch" in err, err.strip())
    rc, _, err, _ = _run(["x"])
    check("no ext", rc == 2, err.strip())
    _unstub("render_tex", "render_mpl")


# ---------------------------------------------------------------- mpl 面（可选）

try:
    import fvspec  # render_mpl 已把 assets/mpl 挂上 sys.path
    import render_mpl

    HAVE_MPL = True
except ImportError:
    HAVE_MPL = False


def _run_mpl(argv):
    """跑 render_mpl.main(argv)，捕获 stdout/stderr 与退出码。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = render_mpl.main(argv)
    return rc, out.getvalue(), err.getvalue()


def _write(tmp, name, spec):
    p = Path(tmp) / name
    p.write_text(json.dumps(spec))
    return p


BASE = {
    "version": 1,
    "data": {"d": [{"x": 0, "y": 1}, {"x": 1, "y": 2}, {"x": 2, "y": 3}]},
    "series": [{"kind": "line", "x": "x", "y": "y", "label": "m"}],
    "xaxis": {"label": "step"},
    "yaxis": {"label": "score"},
    "legend": {"loc": "upper left"},
    "meta": {
        "ledger": "line=series m 的 y~x 轨迹",
        "caption": "render contract smoke",
    },
}


def mpl_cli():
    with tempfile.TemporaryDirectory(prefix="fv-render-") as td:
        # 干净 spec：exit 0、ok: 行、无 ERR/warn
        p = _write(
            td,
            "clean.spec.json",
            dict(BASE, output={"path": "clean", "formats": ["png", "svg"]}),
        )
        rc, out, err = _run_mpl([str(p), "--outdir", td])
        check(
            "mpl clean spec",
            rc == 0 and "ok:" in out and "ERR " not in out and "warn " not in out,
            f"rc={rc} out={out.strip()} err={err.strip()}",
        )
        check(
            "mpl artifacts written",
            (Path(td) / "clean.png").exists() and (Path(td) / "clean.svg").exists(),
            "",
        )

        # 仅 warn 级审计问题（缺轴标）：统一格式 warn <rule>:，退出码仍是 0
        spec = dict(BASE)
        spec.pop("xaxis"), spec.pop("yaxis")
        p = _write(td, "warn.spec.json", dict(spec, output={"path": "warn"}))
        rc, out, _ = _run_mpl([str(p)])
        check(
            "mpl warn-only exits 0",
            rc == 0 and "warn missing-axis-label:" in out and "ERR " not in out,
            f"rc={rc} out={out.strip()}",
        )

        # error 级审计问题（log 轴非正数）：ERR <rule>:，退出 1
        spec = dict(
            BASE,
            yaxis={"label": "v", "scale": "log"},
            data={"d": [{"x": 0, "y": 1}, {"x": 1, "y": -2}]},
            output={"path": "err"},
        )
        p = _write(td, "err.spec.json", spec)
        rc, out, _ = _run_mpl([str(p)])
        check(
            "mpl error-severity exits 1",
            rc == 1 and "ERR log-nonpositive-data:" in out,
            f"rc={rc} out={out.strip()}",
        )

        # declared_texts：mathtext 花括号不是模板占位——'$q_{25}$' 照常
        # 声明（add_tpl 曾见 '{' 就跳 → rb-label-diff extra 误报）；
        # 真占位 {n}/{v}/{by_field} 仍跳过
        spec = dict(
            BASE,
            series=[dict(BASE["series"][0], label="$q_{25}$")],
            output={"path": "mathlab"},
        )
        check(
            "declared keeps mathtext braces",
            "$q_{25}$" in fvspec.declared_texts(spec),
            f"{sorted(fvspec.declared_texts(spec))}",
        )
        p = _write(td, "mathlab.spec.json", spec)
        rc, out, _ = _run_mpl([str(p)])
        check(
            "mathtext label no rb-label-diff",
            rc == 0 and "rb-label-diff" not in out,
            f"rc={rc} out={out.strip()}",
        )
        spec = dict(
            BASE,
            series=[dict(BASE["series"][0], label="n={n}")],
            output={"path": "tpllab"},
        )
        check(
            "declared still skips live template",
            "n={n}" not in fvspec.declared_texts(spec),
            f"{sorted(fvspec.declared_texts(spec))}",
        )
        # note 行模板同理：{i} 非行字段的字面 mathtext 声明，{est} 命中
        # 行字段的模板跳过
        spec = dict(
            BASE,
            data={"d": [{"x": 0, "y": 1, "ex": 0, "ey": 1, "est": "a"}]},
            series=[{"kind": "note", "at": {"x": "ex", "y": "ey"}, "text": "$p_{i}$"}],
            output={"path": "notelab"},
        )
        check(
            "declared keeps note mathtext",
            "$p_{i}$" in fvspec.declared_texts(spec),
            f"{sorted(fvspec.declared_texts(spec))}",
        )
        spec["series"][0]["text"] = "{est} CI"
        check(
            "declared skips live note field",
            "{est} CI" not in fvspec.declared_texts(spec),
            f"{sorted(fvspec.declared_texts(spec))}",
        )

        # spec lint：warn lint:<name>: 前缀，不阻断（exit 0）
        # 用 empty-series（where 匹配 0 行）——裸 hex 会同时触发 offpalette error，
        # 不能当「仅 lint」样本
        spec = dict(BASE, output={"path": "lint"})
        spec["series"] = [dict(BASE["series"][0], where={"x": 999})]
        p = _write(td, "lint.spec.json", spec)
        rc, out, _ = _run_mpl([str(p)])
        check(
            "mpl lint warn line",
            rc == 0 and "warn lint:empty-series:" in out and "ERR " not in out,
            f"rc={rc} out={out.strip()}",
        )

        # --no-audit：lint 与审计全跳——拿 error spec 验证，证明不是侥幸干净
        rc, out, _ = _run_mpl([str(Path(td) / "err.spec.json"), "--no-audit"])
        check(
            "mpl --no-audit",
            rc == 0 and "warn lint:" not in out and "ERR " not in out,
            f"rc={rc} out={out.strip()}",
        )

        # spec 错误 → 2；文件不存在 → 2
        p = _write(td, "bad.spec.json", dict(BASE, bogus=1))
        rc, _, err = _run_mpl([str(p)])
        check("mpl spec error exits 2", rc == 2 and "spec error" in err, err.strip())
        rc, _, err = _run_mpl([str(Path(td) / "nope.json")])
        check(
            "mpl missing file exits 2", rc == 2 and "no such file" in err, err.strip()
        )

        # 统一入口端到端：render.py 对真实 .json 走 render_mpl
        p = _write(td, "e2e.spec.json", dict(BASE, output={"path": "e2e"}))
        rc, out, err, _ = _run([str(p)])
        check(
            "render.py json e2e",
            rc == 0 and "ok:" in out and (Path(td) / "e2e.png").exists(),
            f"rc={rc} out={out.strip()} err={err.strip()}",
        )


def main() -> int:
    dispatch()
    if HAVE_MPL:
        mpl_cli()
    else:
        print("SKIP mpl tests: matplotlib not importable (run under uv)")
    print(
        f"===== {len(FAILS)} failed =====" if FAILS else "===== all checks passed ====="
    )
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
