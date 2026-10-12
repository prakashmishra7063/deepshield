"""SSRF-safe HTTP fetching.

* http/https only, default ports only (80/443) unless private fetch is enabled for tests
* every DNS answer must be a globally routable address; the connection is made to the
  vetted IP (no second resolution), so DNS rebinding cannot swap targets
* redirects are followed manually and re-validated hop by hop
* response size and total time are capped; environment proxies are ignored
"""
import ipaddress
import socket
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpcore

from .config import get_settings

USER_AGENT = "DeepShieldAI/1.0 (+content-authenticity-check; respects robots and platform terms)"


class FetchError(Exception):
    pass


class BlockedDestination(FetchError):
    pass


def _ip_allowed(ip: ipaddress._BaseAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def resolve_checked(host: str, port: int) -> str:
    settings = get_settings()
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise FetchError(f"Could not resolve host '{host}'") from e
    addrs = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not settings.allow_private_fetch and not _ip_allowed(ip):
            raise BlockedDestination(f"Destination '{host}' resolves to a non-public address and was blocked")
        addrs.append(str(ip))
    if not addrs:
        raise FetchError(f"No addresses for '{host}'")
    return addrs[0]


class GuardedBackend(httpcore.SyncBackend):
    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        ip = resolve_checked(host, port)
        return super().connect_tcp(ip, port, timeout=timeout, local_address=local_address, socket_options=socket_options)


def validate_url(url: str) -> str:
    if len(url) > 4096:
        raise FetchError("URL is too long")
    u = urlparse(url.strip())
    if u.scheme not in ("http", "https"):
        raise BlockedDestination("Only http and https URLs are supported")
    if not u.hostname:
        raise FetchError("URL has no host")
    if u.username or u.password:
        raise BlockedDestination("URLs containing credentials are not allowed")
    port = u.port or (443 if u.scheme == "https" else 80)
    if not get_settings().allow_private_fetch and port not in (80, 443):
        raise BlockedDestination("Only standard web ports (80/443) are allowed")
    # Literal IPs are checked here too (GuardedBackend checks again at connect time).
    try:
        ip = ipaddress.ip_address(u.hostname.strip("[]"))
        if not get_settings().allow_private_fetch and not _ip_allowed(ip):
            raise BlockedDestination("Destination address is not public")
    except ValueError:
        pass
    return u.geturl()


@dataclass
class FetchResult:
    url: str
    status: int
    content_type: str
    data: bytes
    truncated: bool = False


def safe_fetch(url: str, *, max_bytes: int | None = None, accept: str = "*/*") -> FetchResult:
    s = get_settings()
    max_bytes = max_bytes or s.max_fetch_mb * 1024 * 1024
    deadline = time.monotonic() + s.fetch_timeout_s * 2
    timeouts = {"connect": s.fetch_timeout_s, "read": s.fetch_timeout_s, "write": s.fetch_timeout_s,
                "pool": s.fetch_timeout_s}
    current = validate_url(url)
    with httpcore.ConnectionPool(network_backend=GuardedBackend(), max_connections=4, retries=0) as pool:
        for _ in range(s.max_redirects + 1):
            headers = [(b"User-Agent", USER_AGENT.encode()), (b"Accept", accept.encode()),
                       (b"Accept-Encoding", b"identity")]
            try:
                with pool.stream("GET", current, headers=headers, extensions={"timeout": timeouts}) as resp:
                    hdrs = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in resp.headers}
                    if resp.status in (301, 302, 303, 307, 308):
                        loc = hdrs.get("location")
                        if not loc:
                            raise FetchError("Redirect without a Location header")
                        current = validate_url(urljoin(current, loc))
                        continue
                    if resp.status >= 400:
                        raise FetchError(f"Remote server returned HTTP {resp.status}")
                    declared = int(hdrs.get("content-length", "0") or 0)
                    if declared > max_bytes:
                        raise FetchError(f"Remote content is larger than the {max_bytes // (1024 * 1024)} MB limit")
                    buf = bytearray()
                    truncated = False
                    for chunk in resp.iter_stream():
                        buf.extend(chunk)
                        if len(buf) > max_bytes:
                            truncated = True
                            break
                        if time.monotonic() > deadline:
                            raise FetchError("Download took too long")
                    return FetchResult(current, resp.status, hdrs.get("content-type", "").split(";")[0].strip().lower(),
                                       bytes(buf[:max_bytes]), truncated)
            except (httpcore.TimeoutException,) as e:
                raise FetchError("Connection timed out") from e
            except httpcore.ConnectError as e:
                if isinstance(e.__context__, BlockedDestination):
                    raise e.__context__ from None
                raise FetchError("Could not connect to the remote server") from e
            except (httpcore.ProtocolError, httpcore.NetworkError, httpcore.UnsupportedProtocol) as e:
                raise FetchError(f"Network error: {type(e).__name__}") from e
        raise FetchError("Too many redirects")
