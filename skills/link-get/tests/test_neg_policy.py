# test_neg_policy.py — neg 写政策统一回归（Phase0 §1.6 / §3.4 transient 类）：
#   generic/wechat 全车道失败 = transient——只记 lane 账（z_lfail），
#   不写内容级 'unavailable' 15min 墓碑。旧行为：exit5 前 z_note 内容键。
# 车道用 PATH stub 强制全挂（dep 伪在但失败 → 走 z_lfail 分支），零外网。
# Run:
#   TMPDIR=$HOME/.cache/lgc-tmp uv run --with pytest pytest skills/link-get/tests/test_neg_policy.py -x -q

import os
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(__file__)
CONN = os.path.join(HERE, "..", "scripts", "connectors")
GENERIC = os.path.join(CONN, "generic-get")
WECHAT = os.path.join(CONN, "wechat-get")
YOUTUBE = os.path.join(CONN, "youtube-get")
BILIBILI = os.path.join(CONN, "bilibili-get")
LGC = os.path.join(HERE, "..", "scripts", "lgc")
TMPBASE = os.path.expanduser("~/.cache")


@pytest.fixture
def stubbin():
    """假车道依赖：binary 存在但必败（exit1 无产物）→ 各车道走 z_lfail 分支。"""
    d = tempfile.mkdtemp(prefix="stubbin-", dir=TMPBASE)
    for name in ("npx", "uv", "curl", "tvly-hikari", "yt-dlp"):
        p = os.path.join(d, name)
        with open(p, "w") as f:
            f.write("#!/bin/sh\nexit 1\n")
        os.chmod(p, 0o755)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _env(home, stubbin):
    e = dict(os.environ)
    e["LGC_HOME"] = home
    e["LGC_BIN"] = LGC
    e["LGC_CONFIG"] = os.path.join(home, "no-config")
    e["PATH"] = stubbin + os.pathsep + e["PATH"]
    e.pop("LGC_OFF", None)
    e.pop("LGC_REFRESH", None)
    e.pop("FIRECRAWL_API_KEY", None)  # firecrawl 走 dep-absent 分支
    return e


def _lgc(env, *a):
    return subprocess.run(
        [sys.executable, LGC, *list(a)], env=env, capture_output=True, text=True
    )


def _run(connector, stubbin, key_prefix):
    home = tempfile.mkdtemp(prefix="lgc-home-", dir=TMPBASE)
    out = tempfile.mkdtemp(prefix="neg-out-", dir=TMPBASE)
    try:
        env = _env(home, stubbin)
        url = "http://example.com/transient-target"
        r = subprocess.run(
            [connector, url, "-o", out],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return r, env, key_prefix + url
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_generic_transient_no_content_tombstone(stubbin):
    r, env, key = _run(GENERIC, stubbin, "article:")
    try:
        assert r.returncode == 5, f"{r.stdout}\n{r.stderr}"
        # 内容键不落日碑：get → rc1 纯 miss（旧政策会给 rc5 unavailable）
        g = _lgc(env, "get", "link-get", key)
        assert g.returncode == 1, f"content key should stay miss: {g.stdout}{g.stderr}"
        # 车道账仍在：lane×key neg → probe rc1（transient 记账不丢）
        for lane in ("defuddle", "trafi", "jina", "firecrawl"):
            p = _lgc(env, "lane", "link-get", "probe", lane, key)
            assert p.returncode == 1, f"lane {lane} should carry lane-fail neg"
    finally:
        shutil.rmtree(env["LGC_HOME"], ignore_errors=True)


def test_wechat_transient_no_content_tombstone(stubbin):
    r, env, key = _run(WECHAT, stubbin, "wechat:")
    try:
        assert r.returncode == 5, f"{r.stdout}\n{r.stderr}"
        g = _lgc(env, "get", "link-get", key)
        assert g.returncode == 1, f"content key should stay miss: {g.stdout}{g.stderr}"
        for lane in ("defuddle", "tvly", "firecrawl"):
            p = _lgc(env, "lane", "link-get", "probe", lane, key)
            assert p.returncode == 1, f"lane {lane} should carry lane-fail neg"
    finally:
        shutil.rmtree(env["LGC_HOME"], ignore_errors=True)


def test_permanent_tombstone_still_written(stubbin):
    """对照组：确认型 permanent（delguard 删除签名）仍写内容 neg → get rc4。"""
    home = tempfile.mkdtemp(prefix="lgc-home-", dir=TMPBASE)
    out = tempfile.mkdtemp(prefix="neg-out-", dir=TMPBASE)
    try:
        env = _env(home, stubbin)
        # defuddle stub 产出含删除签名的 md → z_store delguard → z_note deleted
        with open(os.path.join(stubbin, "npx"), "w") as f:
            f.write(
                "#!/bin/sh\n"
                "while [ $# -gt 0 ]; do\n"
                '  if [ "$1" = -o ]; then\n'
                "    printf 'Title: x 该内容已被发布者删除\\n' > \"$2\"\n"
                "    exit 0\n"
                "  fi\n"
                "  shift\n"
                "done\n"
                "exit 1\n"
            )
        os.chmod(os.path.join(stubbin, "npx"), 0o755)
        url = "http://example.com/gone-article"
        r = subprocess.run(
            [GENERIC, url, "-o", out],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 4, f"{r.stdout}\n{r.stderr}"
        g = _lgc(env, "get", "link-get", "article:" + url)
        assert g.returncode == 4  # deleted 墓碑仍在
    finally:
        shutil.rmtree(out, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


# --- youtube/bilibili 字幕链 transient 同政策 ------------------------------
# meta 拉到（证有轨）但字幕车道全挂 = transient：exit5 + 只记 lane 账，
# 不落 yt:text/bili:subs 内容墓碑。旧行为：z_note ... unavailable。


def _ytdlp_meta_stub(stubbin):
    """yt-dlp：-J 吐带轨元数据（meta 取证成功），其余调用（--write-subs 等）全挂。"""
    p = os.path.join(stubbin, "yt-dlp")
    with open(p, "w") as f:
        f.write(
            "#!/bin/sh\n"
            'for a in "$@"; do\n'
            '  if [ "$a" = "-J" ]; then\n'
            '    printf \'%s\' \'{"title":"stub","subtitles":{"en":[{"ext":"srt"}]}}\'\n'
            "    exit 0\n"
            "  fi\n"
            "done\n"
            "exit 1\n"
        )
    os.chmod(p, 0o755)


def test_youtube_transient_no_content_tombstone(stubbin):
    _ytdlp_meta_stub(stubbin)
    home = tempfile.mkdtemp(prefix="lgc-home-", dir=TMPBASE)
    out = tempfile.mkdtemp(prefix="neg-out-", dir=TMPBASE)
    try:
        env = _env(home, stubbin)
        vid = "dQw4w9WgXcQ"
        url = f"https://www.youtube.com/watch?v={vid}"
        r = subprocess.run(
            [YOUTUBE, url, "-o", out],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert r.returncode == 5, f"{r.stdout}\n{r.stderr}"
        key = "yt:text:" + vid
        g = _lgc(env, "get", "link-get", key)
        assert g.returncode == 1, f"content key should stay miss: {g.stdout}{g.stderr}"
        # transient 记账不丢：两条字幕车道都记 lane×key neg
        for lane in ("yt-transcript", "yt-dlp"):
            p = _lgc(env, "lane", "link-get", "probe", lane, key)
            assert p.returncode == 1, f"lane {lane} should carry lane-fail neg"
    finally:
        shutil.rmtree(out, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


def test_bilibili_transient_no_content_tombstone(stubbin):
    _ytdlp_meta_stub(stubbin)
    # BBDown 伪在但必败 → 车道真跑过 → 也计 lane-fail
    p = os.path.join(stubbin, "BBDown")
    with open(p, "w") as f:
        f.write("#!/bin/sh\nexit 1\n")
    os.chmod(p, 0o755)
    home = tempfile.mkdtemp(prefix="lgc-home-", dir=TMPBASE)
    out = tempfile.mkdtemp(prefix="neg-out-", dir=TMPBASE)
    try:
        env = _env(home, stubbin)
        bvid = "BV1xx411c7mD"
        url = f"https://www.bilibili.com/video/{bvid}/"
        r = subprocess.run(
            [BILIBILI, url, "-o", out],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert r.returncode == 5, f"{r.stdout}\n{r.stderr}"
        key = f"bili:subs:{bvid}:p1"
        g = _lgc(env, "get", "link-get", key)
        assert g.returncode == 1, f"content key should stay miss: {g.stdout}{g.stderr}"
        for lane in ("yt-dlp", "bbdown"):
            p = _lgc(env, "lane", "link-get", "probe", lane, key)
            assert p.returncode == 1, f"lane {lane} should carry lane-fail neg"
    finally:
        shutil.rmtree(out, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)
