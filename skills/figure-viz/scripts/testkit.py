"""testkit.py — figure-viz 测试脚本公共薄层。

三件套：共享 ``FAILS`` 列表、``check(name, cond, detail)``（打 PASS/FAIL
并把失败名+细节收进 FAILS）、``warnings_of(fig)``（取 spec 渲染 lint 警告
``fig.fvspec_report["warnings"]``）。``from testkit import FAILS`` 绑的是
同一列表对象——各测试的 main 末尾照常读 ``len(FAILS)`` 出汇总行（尾部
格式各脚本本来就不统一，不进公共层）。
"""

FAILS = []


def check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), name, detail if not cond else "")
    if not cond:
        FAILS.append(f"{name}: {detail}")


def warnings_of(fig):
    return fig.fvspec_report["warnings"]
