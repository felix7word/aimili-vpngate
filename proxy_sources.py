#!/usr/bin/env python3
"""Fetch free HTTP/SOCKS5 proxy lists from multiple sources."""
from __future__ import annotations

import socket
import time
import urllib.request
from typing import Any

SOURCES: list[dict[str, Any]] = [
    {"name": "proxyscrape_http", "url": "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=us&ssl=all&anonymity=all", "type": "http", "parser": "plain"},
    {"name": "proxyscrape_socks5", "url": "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000&country=us", "type": "socks5", "parser": "plain"},
    {"name": "jetkai_http", "url": "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt", "type": "http", "parser": "plain"},
    {"name": "jetkai_socks5", "url": "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt", "type": "socks5", "parser": "plain"},
    {"name": "speedx_socks5", "url": "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt", "type": "socks5", "parser": "plain"},
]

def fetch_url(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ProxyCollector/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")

def parse_plain(text: str) -> list[tuple[str, int]]:
    results: list[tuple[str, int]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "!", ";")):
            continue
        if ":" in line:
            parts = line.rsplit(":", 1)
            if len(parts) == 2 and parts[1].isdigit():
                results.append((parts[0], int(parts[1])))
    return results

def fetch_all_proxies() -> list[dict[str, Any]]:
    """Fetch from all sources, deduplicate by ip:port:type."""
    seen: set[tuple[str, int, str]] = set()
    proxies: list[dict[str, Any]] = []

    for src in SOURCES:
        try:
            text = fetch_url(src["url"])
            entries = parse_plain(text)
            count = 0
            for ip, port in entries:
                key = (ip, port, src["type"])
                if key not in seen:
                    seen.add(key)
                    proxies.append({
                        "ip": ip,
                        "port": port,
                        "type": src["type"],
                        "source": src["name"],
                    })
                    count += 1
            print(f"[proxy_sources] {src['name']}: 获取 {len(entries)} 个, 新增 {count} 个", flush=True)
        except Exception as e:
            print(f"[proxy_sources] {src['name']} 失败: {e}", flush=True)
        time.sleep(0.5)

    print(f"[proxy_sources] 共获取 {len(proxies)} 个代理（去重后）", flush=True)
    return proxies

def test_proxy_connectivity(host: str, port: int, proxy_type: str, timeout: float = 8) -> int:
    """Test if a proxy is reachable and usable. Returns latency_ms or 0 on failure."""
    started = time.time()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect((host, port))

        if proxy_type == "socks5":
            sock.sendall(b"\x05\x01\x00")
            resp = sock.recv(2)
            if resp != b"\x05\x00":
                return 0
            ip4 = socket.inet_aton("8.8.8.8")
            sock.sendall(b"\x05\x01\x00\x01" + ip4 + (53).to_bytes(2, "big"))
            buf = sock.recv(10)
            if len(buf) < 2 or buf[1] != 0x00:
                return 0

        elif proxy_type == "http":
            req = b"CONNECT 8.8.8.8:53 HTTP/1.1\r\nHost: 8.8.8.8:53\r\n\r\n"
            sock.sendall(req)
            resp = b""
            while b"\r\n\r\n" not in resp:
                chunk = sock.recv(4096)
                if not chunk:
                    return 0
                resp += chunk
            if b"200" not in resp.split(b"\r\n")[0]:
                return 0

        return max(1, int((time.time() - started) * 1000))

    except OSError:
        return 0
    finally:
        try:
            sock.close()
        except Exception:
            pass
