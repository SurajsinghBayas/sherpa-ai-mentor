"""Production guardrails shared by the routers: rate limits, outbound-URL (SSRF) checks,
and validation of the git sources we clone.

The rate limiter is in-process: correct for one API instance. With several replicas each
keeps its own counts, so the effective limit is multiplied by the replica count.
"""
import ipaddress
import logging
import re
import socket
import threading
import time
from urllib.parse import urlparse, urlunparse

from fastapi import HTTPException, Request

from .config import settings

log = logging.getLogger(__name__)


# ── rate limiting ─────────────────────────────────────────────────────────────
class RateLimiter:
    """Fixed-window counters keyed by (bucket, who). Thread-safe; stale keys are pruned."""

    def __init__(self, max_keys: int = 50_000):
        self._hits: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()
        self._max_keys = max_keys
        self._last_prune = time.monotonic()

    def hit(self, key: str, limit: int, window: float) -> float:
        """Count one request; return 0 if allowed, else seconds until the window resets."""
        now = time.monotonic()
        with self._lock:
            if now - self._last_prune > 60 or len(self._hits) > self._max_keys:
                self._prune(now)
            count, start = self._hits.get(key, (0, now))
            if now - start >= window:
                count, start = 0, now
            count += 1
            self._hits[key] = (count, start)
            return 0.0 if count <= limit else max(1.0, window - (now - start))

    def _prune(self, now: float) -> None:
        # windows are at most an hour; anything older can go
        self._hits = {k: v for k, v in self._hits.items() if now - v[1] < 3600}
        self._last_prune = now

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    # uvicorn --proxy-headers already rewrote request.client from X-Forwarded-For
    return request.client.host if request.client else "unknown"


def enforce(request: Request, bucket: str, limit: int, window: float = 60, who: str | None = None) -> None:
    """429 with Retry-After once `who` (default: client IP) exceeds `limit` per `window` seconds."""
    if not settings.rate_limits_enabled:
        return
    who = who or client_ip(request)
    wait = limiter.hit(f"{bucket}:{who}", limit, window)
    if wait:
        log.warning("rate limit: bucket=%s who=%s", bucket, who)
        raise HTTPException(429, f"too many requests; try again in {int(wait)}s",
                            headers={"Retry-After": str(int(wait))})


def ip_limit(bucket: str, limit: int, window: float = 60):
    """FastAPI dependency: per-IP limit for unauthenticated routes (sign-in, sign-up)."""
    def dep(request: Request) -> None:
        enforce(request, bucket, limit, window)
    return dep


# ── outbound URLs (SSRF) ──────────────────────────────────────────────────────
def _is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


def check_outbound_url(url: str) -> str:
    """Validate a user-supplied URL the server will call (custom LLM endpoints).

    In production it must be https and resolve only to public addresses, so users can't
    make the API probe its own network (cloud metadata, the database, localhost).
    In development, http and private hosts are allowed so a local Ollama works.
    """
    url = url.strip().rstrip("/")
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise HTTPException(422, "base_url must be an http(s):// URL")
    if p.username or p.password:
        raise HTTPException(422, "put credentials in the API key field, not in the URL")
    if not settings.is_production:
        return url
    if p.scheme != "https":
        raise HTTPException(422, "base_url must use https://")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or 443, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        raise HTTPException(422, f"can't resolve host {p.hostname!r}")
    if not infos or not all(_is_public(i[4][0]) for i in infos):
        log.warning("ssrf: blocked endpoint host=%s", p.hostname)
        raise HTTPException(422, "base_url must point at a public internet host")
    return url


# ── git sources ───────────────────────────────────────────────────────────────
GIT_HOSTS = ("github.com", "gitlab.com", "bitbucket.org")
_REPO_PATH = re.compile(r"^/[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+){1,4}(\.git)?/?$")
_BRANCH = re.compile(r"^(?!-)(?!.*\.\.)[A-Za-z0-9._/-]{1,200}$")


def normalize_repo_url(raw: str) -> str:
    """https://<public code host>/<owner>/<repo> only: no credentials, query, or odd paths."""
    p = urlparse(raw.strip())
    if p.scheme != "https":
        raise HTTPException(422, "repo_url must be an https:// URL")
    host = (p.hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in GIT_HOSTS):
        raise HTTPException(422, "only github.com, gitlab.com, and bitbucket.org are supported")
    if p.username or p.password:
        raise HTTPException(422, "remove credentials from repo_url; only public repositories are supported")
    if p.port not in (None, 443):
        raise HTTPException(422, "repo_url must not set a port")
    path = p.path
    for suffix in ("/tree/", "/blob/", "/-/tree/"):  # pasted browser links
        if suffix in path:
            path = path.split(suffix, 1)[0]
    if not _REPO_PATH.match(path) or any(seg.strip(".") == "" for seg in path.strip("/").split("/")):
        raise HTTPException(422, "repo_url must look like https://github.com/owner/repo")
    return urlunparse(("https", host, path.rstrip("/"), "", "", ""))


def check_branch(branch: str) -> str:
    branch = (branch or "").strip()
    if branch and not _BRANCH.match(branch):
        raise HTTPException(422, "invalid branch name")
    return branch
