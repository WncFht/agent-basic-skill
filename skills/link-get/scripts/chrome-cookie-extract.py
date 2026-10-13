#!/usr/bin/env python3
# chrome-cookie-extract.py —— 在 Mac 上从 Chrome 提取指定域名的 cookie（在 fht-mba 上运行）。
#
#   python3 chrome-cookie-extract.py --domain '%zhihu%' --format header -o /tmp/zhihu_cookie.txt
#   python3 chrome-cookie-extract.py --domain '%bilibili%' --format netscape -o /tmp/bili.txt
#
# format=header   → "name=value; name=value"（喂 auth-zhihu.sh --cookie / -c）
# format=netscape → Netscape HTTP Cookie File（喂 yt-dlp --cookies）
# 结果只写文件（chmod 600），不回显任何值。
import argparse
import hashlib
import os
import sqlite3
import subprocess
import urllib.parse

ap = argparse.ArgumentParser()
ap.add_argument("--domain", required=True, help="sqlite LIKE 模式，如 '%%zhihu%%'")
ap.add_argument("--format", choices=["header", "netscape"], default="header")
ap.add_argument("-o", "--output", required=True)
ap.add_argument("--profile", default="Default", help="Chrome profile 目录名")
a = ap.parse_args()

pw = subprocess.run(
    [
        "security",
        "find-generic-password",
        "-s",
        "Chrome Safe Storage",
        "-a",
        "Chrome",
        "-w",
    ],
    capture_output=True,
    text=True,
).stdout.strip()
if not pw:
    raise SystemExit("取不到 Chrome Safe Storage 口令——先 security unlock-keychain")
key = hashlib.pbkdf2_hmac("sha1", pw.encode(), b"saltysalt", 1003, 16)
iv = b" " * 16

db = os.path.expanduser(
    f"~/Library/Application Support/Google/Chrome/{a.profile}/Cookies"
)
uri = "file:" + urllib.parse.quote(db) + "?immutable=1"
con = sqlite3.connect(uri, uri=True)
rows = con.execute(
    "SELECT host_key, name, value, hex(encrypted_value), path, expires_utc, is_secure "
    "FROM cookies WHERE host_key LIKE ?",
    (a.domain,),
).fetchall()


def decrypt(host, value, ev):
    if value:
        return value
    blob = bytes.fromhex(ev) if ev else b""
    if not blob.startswith(b"v10"):
        return None
    dec = subprocess.run(
        ["openssl", "enc", "-d", "-aes-128-cbc", "-K", key.hex(), "-iv", iv.hex()],
        input=blob[3:],
        capture_output=True,
    ).stdout
    if dec[:32] == hashlib.sha256(host.encode()).digest():
        dec = dec[32:]
    try:
        return dec.decode()
    except UnicodeDecodeError:
        return None


skipped = 0
if a.format == "header":
    parts = []
    for host, name, value, ev, path, exp, secure in rows:
        v = decrypt(host, value, ev)
        if v is None:
            skipped += 1
            continue
        parts.append(f"{name}={v}")
    body = "; ".join(parts) + "\n"
else:
    lines = ["# Netscape HTTP Cookie File", "# extracted from Mac Chrome"]
    for host, name, value, ev, path, exp, secure in rows:
        v = decrypt(host, value, ev)
        if v is None:
            skipped += 1
            continue
        unix_exp = int(exp / 1e6 - 11644473600) if exp else 0
        flag = "TRUE" if host.startswith(".") else "FALSE"
        sec = "TRUE" if secure else "FALSE"
        lines.append("\t".join([host, flag, path, sec, str(unix_exp), name, v]))
    body = "\n".join(lines) + "\n"
    parts = [line.split("\t")[5] for line in lines if "\t" in line]

with open(a.output, "w") as fh:
    fh.write(body)
os.chmod(a.output, 0o600)
names = {p.split("=", 1)[0] for p in parts}
print(f"cookies: {len(parts)}, skipped {skipped} -> {a.output}")
print("names:", " ".join(sorted(names)))
