# test_lgc.py — lgc contract matrix. Run:
#   TMPDIR=$HOME/.cache/lgc-tmp uv run --with pytest pytest skills/link-get/tests -x -q
# All temp dirs land under $HOME/.cache (never /tmp — tmpfs is full).

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

import pytest

LGC = os.path.join(os.path.dirname(__file__), "..", "scripts", "lgc")
TMPBASE = os.path.expanduser("~/.cache")


@pytest.fixture
def env(tmp_path):
    home = tempfile.mkdtemp(prefix="lgc-test-", dir=TMPBASE)
    e = dict(os.environ)
    e["LGC_HOME"] = home
    e.pop("LGC_OFF", None)
    e.pop("LGC_REFRESH", None)
    e.pop("LGC_STORE_KEY", None)
    e["LGC_CONFIG"] = os.path.join(home, "no-config")
    yield e, home
    shutil.rmtree(home, ignore_errors=True)


def run(env, *a, inp=None):
    return subprocess.run(
        [sys.executable, LGC, *a], env=env, capture_output=True, text=True, input=inp
    )


def wfile(d, name, data="x"):
    p = os.path.join(d, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(data)
    return p


# --- rc contract ------------------------------------------------------------


def test_rc_table(env):
    e, home = env
    k = "article:https://ex.com/a"
    assert run(e, "get", "link-get", k).returncode == 1
    assert run(e, "get", "link-get", k, "--claim").returncode == 6
    run(e, "release", "link-get", k)
    f = wfile(home, "x.md")
    assert run(e, "put", "link-get", k, "--files", f).returncode == 0
    assert run(e, "get", "link-get", k).returncode == 0
    run(e, "neg", "link-get", "article:d", "--reason", "deleted")
    assert run(e, "get", "link-get", "article:d").returncode == 4
    run(e, "neg", "link-get", "article:n", "--reason", "notrack")
    assert run(e, "get", "link-get", "article:n").returncode == 3
    run(e, "neg", "link-get", "article:u", "--reason", "unavailable")
    assert run(e, "get", "link-get", "article:u").returncode == 5
    # second claimer on live marker, tiny wait → 7
    assert run(e, "get", "link-get", "article:w", "--claim").returncode == 6
    assert (
        run(e, "get", "link-get", "article:w", "--claim", "--wait", "1").returncode == 7
    )


def test_concurrent_put_no_tear(env):
    e, home = env
    k = "article:https://ex.com/conc"
    f1 = wfile(home, "a.md", "AAAA")
    f2 = wfile(home, "b.md", "BBBBBB")
    ps = [
        subprocess.Popen(
            [sys.executable, LGC, "put", "link-get", k, "--files", f],
            env=e,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for f in (f1, f2) * 4
    ]
    for p in ps:
        p.wait(30)
    r = run(e, "get", "link-get", k, "--into", os.path.join(home, "o"))
    assert r.returncode == 0
    got = sorted(os.listdir(os.path.join(home, "o")))
    assert got in (["a.md"], ["b.md"])  # one coherent version wins


def test_kill9_no_hang(env):
    e, home = env
    k = "article:https://ex.com/k9"
    p = subprocess.Popen(
        [sys.executable, LGC, "get", "link-get", k, "--claim", "--owner-pid", "999999"],
        env=e,
    )
    p.wait(10)
    # marker owned by a dead pid → steal must succeed fast (no hang)
    r = run(e, "get", "link-get", k, "--claim", "--wait", "3")
    assert r.returncode == 6  # dead owner pid → stolen


def test_partial_clear_degrades(env):
    e, home = env
    k = "article:https://ex.com/pc"
    f = wfile(home, "m.md")
    run(e, "put", "link-get", k, "--files", f)
    blobs = os.path.join(home, "link-get", "blobs")
    for dp, _, fns in os.walk(blobs):
        for fn in fns:
            if fn != "manifest.json":
                os.remove(os.path.join(dp, fn))
    assert run(e, "get", "link-get", k).returncode == 1


def test_neg_never_covers_pos(env):
    e, home = env
    k = "article:https://ex.com/nc"
    f = wfile(home, "m.md")
    run(e, "put", "link-get", k, "--files", f)
    run(e, "neg", "link-get", k, "--reason", "deleted")
    assert run(e, "get", "link-get", k).returncode == 0


def test_denylist(env):
    e, home = env
    secret = wfile(home, "BBDown.data", "SESSDATA=xyz")
    dot = wfile(home, ".hidden", "x")
    ok = wfile(home, "ok.md", "x")
    k = "article:https://ex.com/dl"
    assert run(e, "put", "link-get", k, "--files", secret, dot, ok).returncode == 0
    run(e, "get", "link-get", k, "--into", os.path.join(home, "o"))
    assert os.listdir(os.path.join(home, "o")) == ["ok.md"]
    blobs = os.path.join(home, "link-get", "blobs")
    for dp, _, fns in os.walk(blobs):
        for fn in fns:
            assert "BBDown" not in fn
            assert not fn.startswith(".")


def test_deletion_signature(env):
    e, home = env
    for sig in ("该内容已被发布者删除", "此内容因违规无法查看", "没有知识存在的荒原"):
        f = wfile(home, "del.md", "prefix" + sig)
        assert run(e, "put", "link-get", "article:dels", "--files", f).returncode == 4
    assert run(e, "get", "link-get", "article:dels").returncode == 1


def test_steal_dead_owner(env):
    e, home = env
    k = "article:https://ex.com/steal"
    assert (
        run(e, "get", "link-get", k, "--claim", "--owner-pid", "999999").returncode == 6
    )  # dead pid owner
    assert run(e, "get", "link-get", k, "--claim").returncode == 6  # stolen


def test_prune_expired_and_tmp(env):
    e, home = env
    k = "article:https://ex.com/ttl"
    f = wfile(home, "m.md")
    run(e, "put", "link-get", k, "--files", f, "--ttl", "1")
    time.sleep(1.2)
    assert run(e, "get", "link-get", k).returncode == 1
    # orphan tmp older than 1h
    tdir = os.path.join(home, "link-get", "tmp", "orphan.1")
    os.makedirs(tdir)
    old = time.time() - 3700
    os.utime(tdir, (old, old))
    run(e, "prune", "--ns", "link-get")
    assert not os.path.exists(tdir)


def test_materialize_atomic_chmod(env):
    e, home = env
    k = "article:https://ex.com/mat"
    f1 = wfile(home, "sub/one.md", "1")
    f2 = wfile(home, "two.md", "22")
    run(e, "put", "link-get", k, "--files", f1, f2)
    into = os.path.join(home, "o")
    r = run(e, "get", "link-get", k, "--into", into)
    assert r.returncode == 0
    for n in ("one.md", "two.md"):  # --files flattens to basename
        p = os.path.join(into, n)
        assert os.path.isfile(p)
        assert os.stat(p).st_mode & 0o200  # u+w — never blob's 400
    # --from preserves relative structure
    run(e, "put", "link-get", "article:mat2", "--from", os.path.join(home, "sub"))
    r = run(e, "get", "link-get", "article:mat2", "--into", os.path.join(home, "o2"))
    assert r.returncode == 0
    assert os.path.isfile(os.path.join(home, "o2", "one.md"))


def test_normalize_and_rekey_safety(env):
    e, home = env
    a = run(e, "key", "link-get", "article:https://EX.com/A?utm_x=1&b=2&a=1#f")
    b = run(e, "key", "link-get", "article:https://ex.com/A?a=1&b=2&sn=z")
    assert a.stdout.strip() == b.stdout.strip()
    assert re.fullmatch(r"[0-9a-f]+", a.stdout.strip())


def test_user_version_refuses_write(env):
    e, home = env
    k = "article:https://ex.com/uv"
    f = wfile(home, "m.md")
    run(e, "put", "link-get", k, "--files", f)
    idx = os.path.join(home, "link-get", "index.sqlite3")
    db = sqlite3.connect(idx)
    db.execute("PRAGMA user_version=9")
    db.commit()
    db.close()
    assert run(e, "put", "link-get", "article:x2", "--files", f).returncode == 1
    assert run(e, "get", "link-get", k).returncode == 1  # degrade miss
    db = sqlite3.connect(idx)
    db.execute("PRAGMA user_version=1")
    db.commit()
    db.close()


def test_satisfies_edges(env):
    """验收 #21: 720/cap720→1080 miss; 640/cap1080→720 hit; unknown→miss."""
    e, home = env
    f = wfile(home, "v.mp4", "v")
    run(
        e,
        "put",
        "link-get",
        "media:V1",
        "--files",
        f,
        "--params",
        json.dumps({"height": 720, "req_cap": 720}),
    )
    run(
        e,
        "put",
        "link-get",
        "media:V2",
        "--files",
        f,
        "--params",
        json.dumps({"height": 640, "req_cap": 1080}),
    )
    assert (
        run(
            e, "get", "link-get", "media:V1", "--satisfies", '{"max_height":1080}'
        ).returncode
        == 1
    )
    assert (
        run(
            e, "get", "link-get", "media:V2", "--satisfies", '{"max_height":720}'
        ).returncode
        == 0
    )
    assert (
        run(e, "get", "link-get", "media:V1", "--satisfies", '{"unknown":1}').returncode
        == 1
    )
    # langs: obtained ⊆ req → hit; known-but-not-obtained → miss
    run(
        e,
        "put",
        "link-get",
        "media:V3",
        "--files",
        f,
        "--params",
        json.dumps(
            {
                "height": 720,
                "req_cap": 720,
                "langs_obtained": ["en"],
                "subs_known": ["en", "ja"],
            }
        ),
    )
    assert (
        run(
            e, "get", "link-get", "media:V3", "--satisfies", '{"langs":["en"]}'
        ).returncode
        == 0
    )
    assert (
        run(
            e, "get", "link-get", "media:V3", "--satisfies", '{"langs":["ja"]}'
        ).returncode
        == 1
    )  # known, not obtained
    assert (
        run(
            e, "get", "link-get", "media:V3", "--satisfies", '{"langs":["en","fr"]}'
        ).returncode
        == 0
    )  # fr proven absent


def test_satisfies_generic_equality_arm(env):
    """satisfies 通用等值臂：非 known 断言键走 entry params 同名等值。

    arxivtex satisfies{mode,section,修饰旗标} 全靠此臂——无它则 mode 断言
    永远 REMISS、缓存永不命中。等值→hit；异值→miss；entry 缺同名字段
    （params.get→None）→ miss（D5 缺场即不满足平价，同 {"unknown":1}）。
    """
    e, home = env
    f = wfile(home, "t.tex", "tex")
    run(
        e,
        "put",
        "link-get",
        "arxivtex:2305.1234",
        "--files",
        f,
        "--params",
        json.dumps({"mode": "abstract", "section": "", "no_comments": True}),
    )
    # 同名等值 → hit（本臂之前：非 known 键一律 miss）
    assert (
        run(
            e,
            "get",
            "link-get",
            "arxivtex:2305.1234",
            "--satisfies",
            '{"mode":"abstract"}',
        ).returncode
        == 0
    )
    # 同名异值 → miss（full 束不供 abstract 请求的反向）
    assert (
        run(
            e,
            "get",
            "link-get",
            "arxivtex:2305.1234",
            "--satisfies",
            '{"mode":"full"}',
        ).returncode
        == 1
    )
    # bool 等值 → hit；异值 → miss
    assert (
        run(
            e,
            "get",
            "link-get",
            "arxivtex:2305.1234",
            "--satisfies",
            '{"no_comments":true}',
        ).returncode
        == 0
    )
    assert (
        run(
            e,
            "get",
            "link-get",
            "arxivtex:2305.1234",
            "--satisfies",
            '{"no_comments":false}',
        ).returncode
        == 1
    )
    # entry 缺同名字段 → miss（expand_macros 未上报）
    assert (
        run(
            e,
            "get",
            "link-get",
            "arxivtex:2305.1234",
            "--satisfies",
            '{"expand_macros":false}',
        ).returncode
        == 1
    )


def test_handshake_zero_sideeffect(env):
    e, home = env
    assert run(e, "--version").stdout.strip() == "lgc 1.0"
    r = run(e, "has")
    assert r.returncode == 0
    assert r.stdout.splitlines()[0] == "lgc 1.0"
    for cap in ("get", "satisfies", "cred", "delguard", "kind:lec"):
        assert cap in r.stdout.split()
    assert run(e, "has", "satisfies").returncode == 0
    assert run(e, "has", "bogus").returncode == 1
    assert run(e, "selftest").returncode == 0
    # zero side effects: no ns dirs created by has/version
    assert not os.path.exists(os.path.join(home, "link-get"))


def test_cred_domain_isolation(env):
    e, home = env
    f = wfile(home, "v.mp4", "v")
    run(e, "put", "canvas-skill", "lec:7", "--files", f, "--cred", "tok8aaaa", "--keep")
    assert run(e, "get", "canvas-skill", "lec:7", "--cred", "tok8aaaa").returncode == 0
    assert run(e, "get", "canvas-skill", "lec:7", "--cred", "tok8bbbb").returncode == 1
    assert run(e, "clear", "canvas-skill", "--cred", "tok8aaaa").returncode == 0
    assert run(e, "get", "canvas-skill", "lec:7", "--cred", "tok8aaaa").returncode == 1


def test_lane_semantics(env):
    e, home = env
    assert run(e, "lane", "zhihu-skill", "probe", "tardis", "ans:1").returncode == 0
    run(e, "lane", "zhihu-skill", "note", "tardis", "ans:1", "--reason", "tardis-miss")
    assert run(e, "lane", "zhihu-skill", "probe", "tardis", "ans:1").returncode == 1
    assert (
        run(e, "lane", "zhihu-skill", "probe", "jina", "ans:1").returncode == 0
    )  # other lane unaffected
    for _ in range(3):
        run(e, "lane", "zhihu-skill", "fail", "jina")
    assert run(e, "lane", "zhihu-skill", "probe", "jina").returncode == 1
    run(e, "lane", "zhihu-skill", "hit", "jina")
    assert run(e, "lane", "zhihu-skill", "probe", "jina").returncode == 0


def test_value_roundtrip_and_cat(env):
    e, home = env
    run(e, "put", "link-get", "jwt:t:c", "--value", "tok123", "--ttl", "60")
    r = run(e, "cat", "link-get", "jwt:t:c")
    assert r.returncode == 0
    assert r.stdout == "tok123"
    big = "y" * (70 * 1024)
    run(e, "put", "link-get", "api:t:big", "--value", big)
    r = run(e, "cat", "link-get", "api:t:big")
    assert r.returncode == 0
    assert r.stdout == big


def test_ns_whitelist(env):
    e, home = env
    assert run(e, "get", "evil-ns", "k").returncode == 2
    assert run(e, "put", "evil-ns", "k", "--value", "v").returncode == 2


def test_lgc_off_and_refresh(env):
    e, home = env
    e["LGC_OFF"] = "1"
    assert run(e, "get", "link-get", "article:o").returncode == 1
    assert "cache: off" in run(e, "get", "link-get", "article:o").stderr
    del e["LGC_OFF"]
    f = wfile(home, "m.md")
    run(e, "put", "link-get", "article:r", "--files", f)
    e["LGC_REFRESH"] = "1"
    r = run(e, "get", "link-get", "article:r")
    assert r.returncode in (1, 6, 7)  # refresh skips reads


def test_rekey_keeps_cred_suffix(env):
    """NORM-bump/ rebuild rekey must hash the stored key WITH its '#<cred8>'
    tail — normalize_url eats it as a URL fragment, so URL-form cred rows
    orphaned (keep=1 → permanent leak). Regression for lgc rekey_if_needed."""
    e, home = env
    idx = os.path.join(home, "canvas-skill", "index.sqlite3")
    f = wfile(home, "b.md", "payload")
    k_url = "api:https://oc.sjtu.edu.cn/api/v1/courses/7"  # norm keeps ://
    k_id = "lec:9"  # id-form (lec has no expiry — survives regardless)
    assert (
        run(
            e,
            "put",
            "canvas-skill",
            k_url,
            "--files",
            f,
            "--cred",
            "tok8aaaa",
            "--keep",
        ).returncode
        == 0
    )
    assert (
        run(
            e, "put", "canvas-skill", k_id, "--value", "v9", "--cred", "tok8aaaa"
        ).returncode
        == 0
    )
    kh_url = run(e, "key", "canvas-skill", k_url, "--cred", "tok8aaaa").stdout.strip()
    # force the rekey pass that fires on open when stored norm_version < NORM
    db = sqlite3.connect(idx)
    db.execute("UPDATE counters SET n=0 WHERE name='norm_version'")
    db.commit()
    db.close()
    r = run(
        e,
        "get",
        "canvas-skill",
        k_url,
        "--cred",
        "tok8aaaa",
        "--into",
        os.path.join(home, "o"),
    )
    assert r.returncode == 0  # orphaned pre-fix: kh rewritten credless → miss
    assert os.path.isfile(os.path.join(home, "o", "b.md"))
    assert run(e, "get", "canvas-skill", k_id, "--cred", "tok8aaaa").returncode == 0
    db = sqlite3.connect(idx)
    rows = dict(db.execute("SELECT key,kh FROM entries"))
    db.close()
    assert "api:https://oc.sjtu.edu.cn/api/v1/courses/7#tok8aaaa" in rows
    assert rows["api:https://oc.sjtu.edu.cn/api/v1/courses/7#tok8aaaa"].startswith(
        kh_url
    )  # key cmd prints kh[:16], stored kh is [:24]


def test_lane_auth_cred_scoped(env):
    """auth-class lane fails book under '<lane>#<cred8>' — a dead credential
    must not trip the shared lane breaker for other creds (cred-blind fix)."""
    e, home = env
    idx = os.path.join(home, "zhihu-skill", "index.sqlite3")
    for _ in range(3):
        run(
            e,
            "lane",
            "zhihu-skill",
            "fail",
            "tardis",
            "ans:1",
            "--reason",
            "auth-expired",
            "--cred",
            "tok8aaaa",
        )
    assert (
        run(
            e, "lane", "zhihu-skill", "probe", "tardis", "ans:9", "--cred", "tok8aaaa"
        ).returncode
        == 1
    )
    assert (
        run(
            e, "lane", "zhihu-skill", "probe", "tardis", "ans:9", "--cred", "tok8bbbb"
        ).returncode
        == 0
    )
    assert run(e, "lane", "zhihu-skill", "probe", "tardis").returncode == 0
    db = sqlite3.connect(idx)
    rows = dict(db.execute("SELECT lane,fails FROM breakers").fetchall())
    db.close()
    assert rows == {"tardis#tok8aaaa": 3}  # shared row never written
    # the lane×key neg half of z_lfail scopes the same way
    run(
        e,
        "lane",
        "zhihu-skill",
        "note",
        "jina",
        "ans:5",
        "--reason",
        "auth-expired",
        "--cred",
        "tok8aaaa",
    )
    assert (
        run(
            e, "lane", "zhihu-skill", "probe", "jina", "ans:5", "--cred", "tok8aaaa"
        ).returncode
        == 1
    )
    assert (
        run(
            e, "lane", "zhihu-skill", "probe", "jina", "ans:5", "--cred", "tok8bbbb"
        ).returncode
        == 0
    )
    assert (
        run(
            e, "lane", "zhihu-skill", "probe", "jina", "ans:6", "--cred", "tok8aaaa"
        ).returncode
        == 0
    )
    # lane hit under the dead cred clears only its own scope
    run(e, "lane", "zhihu-skill", "hit", "tardis", "ans:1", "--cred", "tok8aaaa")
    assert (
        run(
            e, "lane", "zhihu-skill", "probe", "tardis", "ans:9", "--cred", "tok8aaaa"
        ).returncode
        == 0
    )


def test_lane_auth_scope_derived_and_shared_unchanged(env):
    """Without --cred the scope derives from the key's cred domain
    (cred8_for): same local credential gated, other creds free. Plain
    `lane fail`/`note` semantics unchanged for existing z_lfail callers."""
    e, home = env
    for _ in range(3):
        run(
            e,
            "lane",
            "zhihu-skill",
            "fail",
            "tardis",
            "ans:1",
            "--reason",
            "auth-expired",
        )
    assert (
        run(e, "lane", "zhihu-skill", "probe", "tardis", "ans:2").returncode == 1
    )  # derived cred8 matches
    assert (
        run(
            e, "lane", "zhihu-skill", "probe", "tardis", "ans:2", "--cred", "other88"
        ).returncode
        == 0
    )
    # regression: shared lane fail still gates every probe, shared lane-neg
    # still keys all creds (z_lfail's 14 call sites unchanged)
    for _ in range(3):
        run(e, "lane", "zhihu-skill", "fail", "jina")
    assert run(e, "lane", "zhihu-skill", "probe", "jina").returncode == 1
    assert (
        run(
            e, "lane", "zhihu-skill", "probe", "jina", "ans:2", "--cred", "other88"
        ).returncode
        == 1
    )
    run(e, "lane", "zhihu-skill", "note", "t2", "ans:1", "--reason", "tardis-miss")
    assert (
        run(
            e, "lane", "zhihu-skill", "probe", "t2", "ans:1", "--cred", "other88"
        ).returncode
        == 1
    )


def test_neg_reason_survives_query_paths(env):
    """ratelimited/auth-expired are real classes: rc stays 5 (append-only)
    but the exact reason must be recoverable — stderr line, --json payload,
    lane-probe passthrough, and cred-scoped content negs."""
    e, home = env
    run(e, "neg", "link-get", "article:rl", "--reason", "ratelimited")
    r = run(e, "get", "link-get", "article:rl")
    assert r.returncode == 5
    assert "neg:ratelimited" in r.stderr
    r = run(e, "get", "link-get", "article:rl", "--json")
    assert r.returncode == 5
    d = json.loads(r.stdout)
    assert d["status"] == "neg"
    assert d["reason"] == "ratelimited"
    r = run(e, "get", "link-get", "article:ua", "--json")
    assert r.returncode == 1  # unknown key stays silent-miss under --json
    run(e, "lane", "zhihu-skill", "note", "jina", "ans:1", "--reason", "ratelimited")
    r = run(e, "lane", "zhihu-skill", "probe", "jina", "ans:1")
    assert r.returncode == 1
    assert "neg:ratelimited" in r.stderr
    # content-level auth-expired neg is cred-scoped by the keyhash suffix
    k = "api:https://x.test/c"
    run(e, "neg", "canvas-skill", k, "--reason", "auth-expired", "--cred", "tok8aaaa")
    r = run(e, "get", "canvas-skill", k, "--cred", "tok8aaaa")
    assert r.returncode == 5
    assert "neg:auth-expired" in r.stderr
    assert run(e, "get", "canvas-skill", k, "--cred", "tok8bbbb").returncode == 1
    # capabilities advertised for caller-side veto
    assert run(e, "has", "reason:ratelimited").returncode == 0
    assert run(e, "has", "reason:auth-expired").returncode == 0
    assert run(e, "has", "lane-cred").returncode == 0


def test_arxivtex_kind_distinct(env):
    """arxivtex is a first-class kind and must NOT collapse onto arxiv —
    'arxiv:tex:<id>' folds to 'arxiv:<id>' (known collapse), but
    'arxivtex:<id>' keeps its own kind prefix through normalization."""
    e, home = env
    k_arxiv = run(e, "key", "link-get", "arxiv:2305.1234").stdout
    assert run(e, "key", "link-get", "arxiv:tex:2305.1234").stdout == k_arxiv
    k_tex = run(e, "key", "link-get", "arxivtex:2305.1234")
    assert k_tex.returncode == 0
    assert re.fullmatch(r"[0-9a-f]+", k_tex.stdout.strip())
    assert k_tex.stdout != k_arxiv
    d = json.loads(run(e, "explain", "link-get", "arxivtex:2305.1234").stdout)
    assert d["norm"] == "arxivtex:2305.1234"  # kind prefix survives NORM
    # URL form extracts the same bare id under the arxivtex kind
    assert (
        run(e, "key", "link-get", "arxivtex:https://arxiv.org/abs/2305.1234").stdout
        == k_tex.stdout
    )
    # in the TTL table → advertised, and neg takes the default reason ttl
    assert run(e, "has", "kind:arxivtex").returncode == 0
    assert (
        run(e, "put", "link-get", "arxivtex:2305.1234", "--value", "tex").returncode
        == 0
    )
    assert run(e, "get", "link-get", "arxivtex:2305.1234").returncode == 0
    assert (
        run(e, "neg", "link-get", "arxivtex:gone", "--reason", "unavailable").returncode
        == 0
    )
    assert run(e, "get", "link-get", "arxivtex:gone").returncode == 5


def test_cred_fp(env):
    """cred-fp prints the cred8 a domain resolves to (same hash content
    scoping uses); empty + rc3 when the domain is unknown or fileless."""
    e, home = env
    e["HOME"] = home  # cred8_for expands ~/.config/* against this HOME
    r = run(e, "cred-fp", "zhihu")
    assert r.returncode == 3
    assert r.stdout == ""
    assert run(e, "cred-fp", "no-such-domain").returncode == 3
    wfile(home, ".config/zhihu-skill/cookie.txt", "COOKIE1")
    fp = hashlib.sha256(b"COOKIE1").hexdigest()[:8]
    r = run(e, "cred-fp", "zhihu")
    assert r.returncode == 0
    assert r.stdout.strip() == fp
    assert run(e, "cred-fp", "zhihu").stdout.strip() == fp  # stable
    # same fp content rows are scoped by: derived put carries '#<fp>'
    run(e, "put", "zhihu-skill", "ans:1", "--value", "v")
    assert f"ans:1#{fp}" in run(e, "list", "zhihu-skill").stdout


def test_prune_dead_cred(env):
    """prune --dead-cred drops rows whose '#<cred8>' scope matches no live
    fingerprint of any known cred domain; live-cred and uncred'd rows stay.
    --dry-run lists without deleting."""
    e, home = env
    e["HOME"] = home
    wfile(home, ".config/zhihu-skill/cookie.txt", "COOKIE1")
    fp = hashlib.sha256(b"COOKIE1").hexdigest()[:8]
    f = wfile(home, "m.md")
    run(e, "put", "zhihu-skill", "ans:live", "--files", f)  # derived → live fp
    run(e, "put", "zhihu-skill", "ans:dead1", "--files", f, "--cred", "deadbeef")
    run(
        e,
        "neg",
        "zhihu-skill",
        "ans:dead2",
        "--reason",
        "auth-expired",
        "--cred",
        "deadbeef",
    )
    run(e, "put", "zhihu-skill", "article:plain", "--files", f)  # no cred domain
    r = run(e, "prune", "--ns", "zhihu-skill", "--dead-cred", "--dry-run")
    assert r.returncode == 0
    assert "ans:dead1#deadbeef" in r.stdout
    assert "ans:dead2#deadbeef" in r.stdout
    assert "ans:live" not in r.stdout
    assert "article:plain" not in r.stdout
    assert "dead-cred: 2" in r.stdout
    # dry-run deleted nothing
    assert (
        run(e, "get", "zhihu-skill", "ans:dead1", "--cred", "deadbeef").returncode == 0
    )
    r = run(e, "prune", "--ns", "zhihu-skill", "--dead-cred")
    assert r.returncode == 0
    assert "dead-cred: 2" in r.stdout
    assert (
        run(e, "get", "zhihu-skill", "ans:dead1", "--cred", "deadbeef").returncode == 1
    )
    assert (
        run(e, "get", "zhihu-skill", "ans:dead2", "--cred", "deadbeef").returncode == 1
    )
    # live-fp and uncred'd rows untouched
    assert run(e, "get", "zhihu-skill", "ans:live").returncode == 0
    assert run(e, "get", "zhihu-skill", "article:plain").returncode == 0
    assert f"ans:live#{fp}" in run(e, "list", "zhihu-skill").stdout
    # nothing left to reap
    assert (
        "dead-cred: 0" in run(e, "prune", "--ns", "zhihu-skill", "--dead-cred").stdout
    )
