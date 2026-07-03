from __future__ import annotations

import base64
import re
import urllib.parse
from typing import Optional

import yaml


def decode_base64(data: str) -> str:
    """Decode Base64 content with padding handling."""
    data = data.strip()
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    try:
        return base64.b64decode(data).decode("utf-8", errors="replace")
    except Exception:
        return data


def parse_ss_uri(uri: str) -> Optional[dict]:
    """Parse a shadowsocks:// URI."""
    try:
        if not uri.startswith("ss://"):
            return None
        rest = uri[5:]
        if "#" in rest:
            rest, name = rest.split("#", 1)
            name = urllib.parse.unquote(name)
        else:
            name = ""
        if "@" in rest:
            # method:password@host:port
            encoded, server = rest.split("@", 1)
            decoded = decode_base64(encoded)
            if ":" in decoded:
                method, password = decoded.split(":", 1)
            else:
                return None
            if ":" in server:
                host, port = server.rsplit(":", 1)
                port = int(port)
            else:
                return None
            return {
                "name": name or f"SS-{host}:{port}",
                "type": "ss",
                "server": host,
                "port": port,
                "cipher": method,
                "password": password,
                "udp": True,
            }
        else:
            # SIP002 format: base64 encoded JSON-like
            decoded = decode_base64(rest.split("#")[0] if "#" not in rest else rest)
            if "@" in decoded:
                method_pass, server = decoded.split("@", 1)
                if ":" in method_pass:
                    method, password = method_pass.split(":", 1)
                else:
                    return None
                if ":" in server:
                    host, port = server.rsplit(":", 1)
                    port = int(port)
                else:
                    return None
                return {
                    "name": name or f"SS-{host}:{port}",
                    "type": "ss",
                    "server": host,
                    "port": port,
                    "cipher": method,
                    "password": password,
                    "udp": True,
                }
    except Exception:
        return None
    return None


def parse_ssr_uri(uri: str) -> Optional[dict]:
    """Parse a ssr:// URI."""
    try:
        if not uri.startswith("ssr://"):
            return None
        encoded = uri[6:]
        decoded = decode_base64(encoded)
        # Format: server:port:protocol:method:obfs:password/?params
        match = re.match(
            r"([^:]+):(\d+):([^:]*):([^:]*):([^:]*):([^/]+)/?(.*)", decoded
        )
        if not match:
            return None
        host = match.group(1)
        port = int(match.group(2))
        protocol = match.group(3)
        method = match.group(4)
        obfs = match.group(5)
        password_b64 = match.group(6)
        password = decode_base64(password_b64)
        params = match.group(7)

        obfs_param = ""
        if "obfsparam=" in params:
            obfs_param_b64 = params.split("obfsparam=")[1].split("&")[0]
            obfs_param = decode_base64(urllib.parse.unquote(obfs_param_b64))

        return {
            "name": f"SSR-{host}:{port}",
            "type": "ssr",
            "server": host,
            "port": port,
            "cipher": method,
            "password": password,
            "protocol": protocol,
            "obfs": obfs,
            "obfs-param": obfs_param,
            "udp": True,
        }
    except Exception:
        return None


def parse_vmess_uri(uri: str) -> Optional[dict]:
    """Parse a vmess:// URI."""
    try:
        if not uri.startswith("vmess://"):
            return None
        raw = uri[8:]
        # Try JSON format
        try:
            decoded = decode_base64(raw)
            data = yaml.safe_load(decoded)
            if isinstance(data, dict):
                return {
                    "name": data.get("ps", f"VMess-{data.get('add', 'unknown')}"),
                    "type": "vmess",
                    "server": data.get("add", ""),
                    "port": int(data.get("port", 0)),
                    "uuid": data.get("id", ""),
                    "alterId": int(data.get("aid", 0)),
                    "cipher": data.get("scy", "auto") or "auto",
                    "tls": data.get("tls", "") == "tls",
                    "network": data.get("net", "tcp"),
                    "ws-path": data.get("path", ""),
                    "ws-headers": {"Host": data.get("host", "")} if data.get("host") else {},
                    "udp": True,
                }
        except Exception:
            pass
        # Try share link format
        try:
            decoded = decode_base64(raw)
            if "?" in decoded:
                return None  # Not fully supported yet
            return None
        except Exception:
            return None
    except Exception:
        return None
    return None


def parse_trojan_uri(uri: str) -> Optional[dict]:
    """Parse a trojan:// URI."""
    try:
        if not uri.startswith("trojan://"):
            return None
        parsed = urllib.parse.urlparse(uri)
        password = parsed.username or ""
        host = parsed.hostname or ""
        port = parsed.port or 443
        name = urllib.parse.unquote(parsed.fragment or "") or f"Trojan-{host}:{port}"
        query = dict(urllib.parse.parse_qsl(parsed.query))
        return {
            "name": name,
            "type": "trojan",
            "server": host,
            "port": port,
            "password": password,
            "sni": query.get("sni", host),
            "skip-cert-verify": query.get("allowInsecure", "0") == "1",
            "udp": True,
        }
    except Exception:
        return None


def parse_vless_uri(uri: str) -> Optional[dict]:
    """Parse a vless:// URI."""
    try:
        if not uri.startswith("vless://"):
            return None
        parsed = urllib.parse.urlparse(uri)
        uuid = parsed.username or ""
        host = parsed.hostname or ""
        port = parsed.port or 443
        name = urllib.parse.unquote(parsed.fragment or "") or f"VLESS-{host}:{port}"
        query = dict(urllib.parse.parse_qsl(parsed.query))
        network = query.get("type", "tcp")
        result = {
            "name": name,
            "type": "vless",
            "server": host,
            "port": port,
            "uuid": uuid,
            "flow": query.get("flow", ""),
            "tls": query.get("security", "") == "tls",
            "network": network,
            "udp": True,
        }
        if query.get("security", "") == "reality":
            result["tls"] = True
            result["reality"] = True
            result["public-key"] = query.get("pbk", "")
            result["short-id"] = query.get("sid", "")
            result["server-name"] = query.get("sni", host)
        if network == "ws":
            result["ws-path"] = query.get("path", "/")
            result["ws-headers"] = {"Host": query.get("host", host)}
        if network == "grpc":
            result["grpc-service-name"] = query.get("serviceName", "")
        return result
    except Exception:
        return None


def parse_uri(uri: str) -> Optional[dict]:
    """Parse a single proxy URI into a Clash-compatible dict."""
    parsers = [parse_ss_uri, parse_ssr_uri, parse_vmess_uri, parse_trojan_uri, parse_vless_uri]
    for parser in parsers:
        result = parser(uri)
        if result:
            return result
    return None


def parse_subscription_text(text: str) -> list[dict]:
    """Parse subscription text content into a list of Clash-compatible proxy dicts.

    Supports: Clash YAML, Base64-encoded URI list, plain URI list.
    """
    text = text.strip()

    # Try Clash YAML format
    if text.startswith(("port:", "proxies:", "mixed-port:", "socks-port:")):
        try:
            data = yaml.safe_load(text)
            if isinstance(data, dict) and "proxies" in data:
                return data["proxies"]
        except Exception:
            pass

    if text.startswith("proxies:"):
        try:
            data = yaml.safe_load(text)
            if isinstance(data, dict) and "proxies" in data:
                return data["proxies"]
        except Exception:
            pass

    # Try as a full Clash config
    if text.startswith("mixed-port:") or text.startswith("port:"):
        try:
            data = yaml.safe_load(text)
            proxies = []
            if "proxies" in data:
                proxies.extend(data["proxies"])
            if "proxy-providers" in data:
                for name, provider in data["proxy-providers"].items():
                    if "proxies" in provider:
                        proxies.extend(provider["proxies"])
            if proxies:
                return proxies
        except Exception:
            pass

    # Try Base64 decode
    try:
        decoded = decode_base64(text)
        # Check if decoded is a Clash config
        if decoded.strip().startswith(("port:", "proxies:", "mixed-port:")):
            try:
                data = yaml.safe_load(decoded)
                if isinstance(data, dict) and "proxies" in data:
                    return data["proxies"]
            except Exception:
                pass
        # Check if decoded contains URIs (one per line or newline separated)
        uri_list = decoded.strip().splitlines()
        proxies = []
        for line in uri_list:
            line = line.strip()
            if line:
                proxy = parse_uri(line)
                if proxy:
                    proxies.append(proxy)
        if proxies:
            return proxies
    except Exception:
        pass

    # Try as plain URI list (one per line or space-separated)
    proxies = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            proxy = parse_uri(line)
            if proxy:
                proxies.append(proxy)
    if proxies:
        return proxies

    # Try space-separated URIs in single line
    for token in text.split():
        token = token.strip()
        if token.startswith(("ss://", "ssr://", "vmess://", "trojan://", "vless://")):
            proxy = parse_uri(token)
            if proxy:
                proxies.append(proxy)

    return proxies


async def fetch_subscription(url: str) -> str | None:
    """Fetch subscription content from URL."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            resp.raise_for_status()
            return resp.text
    except Exception:
        return None
