#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import select
import socket
import sys
import threading
from urllib.parse import urlsplit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ProxyCommand helper that tunnels SSH over a SOCKS5 proxy.")
    parser.add_argument("--proxy", required=True, help="Proxy URL such as socks5://127.0.0.1:7897")
    parser.add_argument("host", help="Target host passed by ssh as %%h")
    parser.add_argument("port", type=int, help="Target port passed by ssh as %%p")
    return parser.parse_args()


def read_exact(sock: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise OSError("Unexpected EOF from SOCKS proxy")
        chunks.extend(chunk)
    return bytes(chunks)


def parse_proxy(proxy_url: str) -> tuple[str, int, bool]:
    parsed = urlsplit(proxy_url)
    scheme = parsed.scheme.lower()
    if scheme not in {"socks5", "socks5h"}:
        raise SystemExit(f"Unsupported proxy scheme: {scheme}")
    if parsed.username or parsed.password:
        raise SystemExit("Username/password SOCKS auth is not supported by this helper")
    host = parsed.hostname
    port = parsed.port or 1080
    if not host:
        raise SystemExit("SOCKS proxy host is missing")
    return host, port, scheme == "socks5h"


def connect_via_socks(proxy_url: str, target_host: str, target_port: int) -> socket.socket:
    proxy_host, proxy_port, remote_dns = parse_proxy(proxy_url)
    sock = socket.create_connection((proxy_host, proxy_port), timeout=10)

    sock.sendall(b"\x05\x01\x00")
    greeting = read_exact(sock, 2)
    if greeting != b"\x05\x00":
        raise OSError(f"SOCKS proxy rejected no-auth negotiation: {greeting!r}")

    if remote_dns:
        host_bytes = target_host.encode("idna")
        request = b"\x05\x01\x00\x03" + bytes([len(host_bytes)]) + host_bytes + target_port.to_bytes(2, "big")
    else:
        try:
            host_bytes = socket.inet_pton(socket.AF_INET, target_host)
            request = b"\x05\x01\x00\x01" + host_bytes + target_port.to_bytes(2, "big")
        except OSError:
            try:
                host_bytes = socket.inet_pton(socket.AF_INET6, target_host)
                request = b"\x05\x01\x00\x04" + host_bytes + target_port.to_bytes(2, "big")
            except OSError:
                resolved = socket.getaddrinfo(target_host, target_port, type=socket.SOCK_STREAM)[0][4][0]
                try:
                    host_bytes = socket.inet_pton(socket.AF_INET, resolved)
                    request = b"\x05\x01\x00\x01" + host_bytes + target_port.to_bytes(2, "big")
                except OSError:
                    host_bytes = socket.inet_pton(socket.AF_INET6, resolved)
                    request = b"\x05\x01\x00\x04" + host_bytes + target_port.to_bytes(2, "big")

    sock.sendall(request)
    header = read_exact(sock, 4)
    version, reply, _reserved, atyp = header
    if version != 5 or reply != 0:
        raise OSError(f"SOCKS connect failed with reply code {reply}")

    if atyp == 1:
        read_exact(sock, 4)
    elif atyp == 3:
        domain_len = read_exact(sock, 1)[0]
        read_exact(sock, domain_len)
    elif atyp == 4:
        read_exact(sock, 16)
    else:
        raise OSError(f"Unsupported SOCKS address type: {atyp}")
    read_exact(sock, 2)
    sock.settimeout(None)
    return sock


def pump_stdin_to_socket(sock: socket.socket) -> None:
    try:
        while True:
            chunk = sys.stdin.buffer.read(65536)
            if not chunk:
                break
            sock.sendall(chunk)
    finally:
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def pump_socket_to_stdout(sock: socket.socket) -> None:
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        sys.stdout.buffer.write(chunk)
        sys.stdout.buffer.flush()


def relay_unix(sock: socket.socket) -> None:
    stdin_fd = sys.stdin.fileno()
    socket_fd = sock.fileno()
    stdin_open = True

    while True:
        read_fds = [socket_fd]
        if stdin_open:
            read_fds.append(stdin_fd)
        ready, _, _ = select.select(read_fds, [], [])

        if socket_fd in ready:
            chunk = sock.recv(65536)
            if not chunk:
                break
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()

        if stdin_open and stdin_fd in ready:
            chunk = os.read(stdin_fd, 65536)
            if not chunk:
                stdin_open = False
                try:
                    sock.shutdown(socket.SHUT_WR)
                except OSError:
                    pass
            else:
                sock.sendall(chunk)


def main() -> int:
    args = parse_args()
    sock = connect_via_socks(args.proxy, args.host, args.port)
    try:
        if os.name != "nt":
            relay_unix(sock)
        else:
            thread = threading.Thread(target=pump_stdin_to_socket, args=(sock,))
            thread.start()
            pump_socket_to_stdout(sock)
            thread.join(timeout=1)
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
