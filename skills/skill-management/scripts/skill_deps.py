#!/usr/bin/env python3
"""skill_deps.py — 扫描 ~/.agents/skills/*/deps.toml，检查/安装/升级 skill 声明的外部依赖。

用法:
  skill_deps.py                     # check：打印依赖状态矩阵；缺必需依赖退出码 1，只缺可选为 2
  skill_deps.py --upgrade [skill..] # 执行各 dep 的 upgrade 命令（不带 skill 名 = 全部）
  skill_deps.py --install [skill..] # 对缺失的 dep 执行 install 命令（不带 skill 名 = 全部）

deps.toml 格式（每个 dep 一节）:
  [[dep]]
  name = "yt-dlp"                # 必填，显示名
  check = "command -v yt-dlp"    # 必填，bash -c 执行，exit 0 = 已装
  version = "yt-dlp --version"   # 可选，stdout 首行作版本显示
  install = "uv tool install yt-dlp"   # 可选
  upgrade = "uv tool upgrade yt-dlp"   # 可选
  optional = true                # 可选，默认 false；缺失只报 WARN 不计退出码

  check/version/install/upgrade 均可写成 { linux = "...", darwin = "..." } 按平台分派，
  未命中平台时该字段视为缺省。命令里的 ~ 由 bash 展开。
"""

import argparse
import os
import subprocess
import sys

try:
    import tomllib
except ImportError:
    sys.exit("skill_deps.py 需要 Python 3.11+（tomllib）")

SKILLS_DIR = os.path.expanduser("~/.agents/skills")
PLAT = "darwin" if sys.platform == "darwin" else "linux"


def pick(v):
    if isinstance(v, dict):
        return v.get(PLAT)
    return v


def run(cmd, timeout=120):
    try:
        return subprocess.run(
            ["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", "check timed out")


def load_manifests():
    out = []
    for base in sorted(os.listdir(SKILLS_DIR)):
        f = os.path.join(SKILLS_DIR, base, "deps.toml")
        if not os.path.isfile(f):
            continue
        try:
            with open(f, "rb") as fh:
                data = tomllib.load(fh)
        except Exception as e:
            print(f"  !! {f} 解析失败: {e}", file=sys.stderr)
            continue
        out.append((base, data.get("dep", [])))
    return out


def check_dep(dep):
    cmd = pick(dep.get("check"))
    if not cmd:
        return None
    return run(cmd).returncode == 0


def version_of(dep):
    cmd = pick(dep.get("version"))
    if not cmd:
        return ""
    r = run(cmd, timeout=30)
    return (
        r.stdout.strip().splitlines()[0][:60]
        if r.returncode == 0 and r.stdout.strip()
        else ""
    )


def cmd_check(manifests, only, quiet=False):
    missing_req = missing_opt = present = 0
    for skill, deps in manifests:
        if only and skill not in only:
            continue
        lines = []
        for dep in deps:
            name = dep.get("name", "?")
            ok = check_dep(dep)
            if ok:
                present += 1
                ver = version_of(dep)
                if not quiet:
                    lines.append(
                        f"  \033[32mOK\033[0m   {name}" + (f"  {ver}" if ver else "")
                    )
            elif ok is None:
                if not quiet:
                    lines.append(f"  \033[2mN/A\033[0m  {name}（本平台不适用）")
            elif dep.get("optional"):
                missing_opt += 1
                hint = pick(dep.get("install")) or ""
                lines.append(
                    f"  \033[33mWARN\033[0m {name} 缺失（可选）"
                    + (f" — {hint}" if hint else "")
                )
            else:
                missing_req += 1
                hint = pick(dep.get("install")) or ""
                lines.append(
                    f"  \033[31mFAIL\033[0m {name} 缺失"
                    + (f" — {hint}" if hint else "")
                )
        if lines or not quiet:
            print(f"== {skill} ==")
            print("\n".join(lines))
    print(f"\n{present} 已装, {missing_req} 必需缺失, {missing_opt} 可选缺失")
    return 1 if missing_req else (2 if missing_opt else 0)


def cmd_act(manifests, only, key, title):
    rc = 0
    for skill, deps in manifests:
        if only and skill not in only:
            continue
        for dep in deps:
            cmd = pick(dep.get(key))
            if not cmd:
                continue
            name = dep.get("name", "?")
            ok = check_dep(dep)
            if key == "install" and ok:
                continue
            if key == "upgrade" and ok is False:
                print(f"[skip] {skill}/{name} 未安装——先跑 --install")
                continue
            print(f"[{title}] {skill}/{name}: {cmd}")
            try:
                r = subprocess.run(["bash", "-c", cmd], timeout=1800)
            except subprocess.TimeoutExpired:
                print(f"  \033[31mFAIL\033[0m {name}（超时）")
                rc = 1
                continue
            # 复核：以 check 重跑结果为准，不只信退出码
            ok2 = check_dep(dep)
            if ok2:
                print(f"  \033[32mOK\033[0m   {name}")
            elif r.returncode == 0 and ok2 is None:
                print(
                    f"  \033[32mOK\033[0m   {name}（命令成功，本平台无 check 可复核）"
                )
            elif r.returncode == 0:
                print(f"  \033[33mWARN\033[0m {name} 命令成功但 check 仍未通过")
                rc = 1
            else:
                print(f"  \033[31mFAIL\033[0m {name}（exit {r.returncode}）")
                rc = 1
    return rc


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--upgrade", nargs="*", metavar="SKILL", help="执行 upgrade 命令")
    ap.add_argument(
        "--install", nargs="*", metavar="SKILL", help="对缺失 dep 执行 install 命令"
    )
    ap.add_argument("--quiet", "-q", action="store_true", help="check 模式只报非 OK 项")
    args = ap.parse_args()

    manifests = load_manifests()
    if args.upgrade is not None:
        sys.exit(cmd_act(manifests, args.upgrade or None, "upgrade", "upgrade"))
    if args.install is not None:
        sys.exit(cmd_act(manifests, args.install or None, "install", "install"))
    sys.exit(cmd_check(manifests, None, args.quiet))


if __name__ == "__main__":
    main()
