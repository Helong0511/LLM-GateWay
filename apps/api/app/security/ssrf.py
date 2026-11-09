"""供应商地址校验。云元数据地址一律拒绝，自建端点必须先进入白名单。"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
import structlog

from app.core.errors import AppError

Resolver = Callable[[str], Awaitable[list[ipaddress.IPv4Address | ipaddress.IPv6Address]]]

_BLOCKED_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)
_METADATA_IPS = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("169.254.170.2"),
    ipaddress.ip_address("100.100.100.200"),
    ipaddress.ip_address("fd00:ec2::254"),
}
_METADATA_HOSTS = {"metadata.google.internal", "metadata.goog"}
_SELF_HOSTED = {"self_hosted", "ollama"}
_REDIRECTS = {301, 302, 303, 307, 308}
logger = structlog.get_logger()


@dataclass(frozen=True)
class AddressDecision:
    host: str
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address


def _unwrap(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _metadata(host: str, ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None) -> bool:
    if host in _METADATA_HOSTS:
        return True
    return ip is not None and _unwrap(ip) in _METADATA_IPS


def _blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    candidate = _unwrap(ip)
    if candidate in _METADATA_IPS:
        return True
    if any(candidate in network for network in _BLOCKED_NETWORKS):
        return True
    return bool(
        candidate.is_private
        or candidate.is_loopback
        or candidate.is_link_local
        or candidate.is_multicast
        or candidate.is_reserved
        or candidate.is_unspecified
    )


def _alert(host: str) -> None:
    logger.warning("ssrf_blocked", host=host, reason="metadata")


async def default_resolver(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    import asyncio

    def lookup() -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise AppError(400, "URL_DNS_FAILED") from exc
        return [ipaddress.ip_address(item[4][0]) for item in infos]

    return await asyncio.get_running_loop().run_in_executor(None, lookup)


async def inspect_url(
    raw_url: str,
    *,
    resolver: Resolver,
    allowlist: set[str],
    endpoint_kind: str,
) -> AddressDecision:
    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise AppError(400, "URL_SCHEME_INVALID")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or "\\" in raw_url:
        raise AppError(400, "URL_HOST_INVALID")
    if _metadata(host, None):
        _alert(host)
        raise AppError(400, "URL_METADATA_BLOCKED")
    try:
        literal: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = [ipaddress.ip_address(host)]
    except ValueError:
        literal = await resolver(host)
    if not literal:
        raise AppError(400, "URL_DNS_FAILED")
    self_hosted = endpoint_kind in _SELF_HOSTED
    host_approved = self_hosted and host in allowlist
    for ip in literal:
        if _metadata(host, ip):
            _alert(host)
            raise AppError(400, "URL_METADATA_BLOCKED")
    covered = host_approved or any(self_hosted and str(ip) in allowlist for ip in literal)
    if self_hosted and not covered:
        raise AppError(400, "URL_ALLOWLIST_REQUIRED")
    for ip in literal:
        ip_approved = host_approved or (self_hosted and str(ip) in allowlist)
        if _blocked(ip) and not ip_approved:
            raise AppError(
                400,
                "URL_ALLOWLIST_REQUIRED" if self_hosted else "URL_PRIVATE_BLOCKED",
            )
    return AddressDecision(host=host, ip=literal[0])


def pinned_url(raw_url: str, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    parsed = urlparse(raw_url)
    host = f"[{ip}]" if isinstance(ip, ipaddress.IPv6Address) else str(ip)
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://{host}{port}{path}{query}"


async def fetch_checked(
    client: httpx.AsyncClient,
    method: str,
    raw_url: str,
    *,
    resolver: Resolver,
    allowlist: set[str],
    endpoint_kind: str,
    headers: dict[str, str] | None = None,
    json_body: object | None = None,
    max_hops: int = 3,
) -> httpx.Response:
    current = raw_url
    for _hop in range(max_hops):
        decision = await inspect_url(current, resolver=resolver, allowlist=allowlist, endpoint_kind=endpoint_kind)
        outbound = dict(headers or {})
        outbound["host"] = decision.host
        response = await client.request(
            method,
            pinned_url(current, decision.ip),
            headers=outbound,
            json=json_body,
            follow_redirects=False,
            extensions={"sni_hostname": decision.host},
        )
        if response.status_code not in _REDIRECTS:
            return response
        location = response.headers.get("location")
        if not location:
            return response
        current = urljoin(current, location)
        json_body = None
        method = "GET" if response.status_code in {301, 302, 303} else method
    raise AppError(400, "URL_REDIRECT_LIMIT")
