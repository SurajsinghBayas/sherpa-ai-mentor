"""Web enrichment via Firecrawl — repo pages + docs sites become cited chunks.

When a GitHub URL is ingested (and FIRECRAWL_API_KEY is set), Sherpa also
scrapes the rendered repo page (description, topics, README) plus any
caller-supplied docs URLs. Results are chunked with `web/…` provenance so
the existing CitationVerifier and UI work unchanged — web claims cite just
like code claims.

No key / any failure → enrichment is skipped gracefully, code-only answers
still work. Nothing here is on the hot Q&A path (ingest-time only).
"""
import re
from urllib.parse import urlparse

import httpx

from .chunk import chunk_file, Chunk
from .config import settings

MAX_SOURCES = 6
MAX_CHARS_PER_SOURCE = 15_000
TIMEOUT_S = 45


def candidate_urls(repo_url: str | None,
                   docs_urls: list[str] | None) -> list[str]:
    """Repo page first, then explicit docs URLs. De-duplicated, capped."""
    urls: list[str] = []
    if repo_url:
        m = re.match(r"https?://github\.com/([^/\s]+/[^/\s]+?)(?:\.git|/)?$", repo_url.strip())
        if m:
            urls.append(f"https://github.com/{m.group(1)}")
    for u in docs_urls or []:
        u = (u or "").strip()
        if u.startswith(("http://", "https://")) and u not in urls:
            urls.append(u)
    return urls[:MAX_SOURCES]


def web_path(url: str) -> str:
    """Stable cited path, e.g. web/github.com/org/repo.md."""
    p = urlparse(url)
    slug = (p.netloc + p.path).strip("/").replace("/", "/")
    slug = re.sub(r"[^a-zA-Z0-9_./-]", "-", slug) or "page"
    if not slug.endswith(".md"):
        slug += ".md"
    return f"web/{slug}"


def firecrawl_scrape(url: str, api_key: str,
                     base_url: str | None = None) -> str | None:
    """Single Firecrawl /v1/scrape call → markdown, or None on any failure."""
    base = (base_url or settings.firecrawl_base_url).rstrip("/")
    try:
        r = httpx.post(
            f"{base}/v1/scrape",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
            timeout=TIMEOUT_S,
        )
        if r.status_code != 200:
            return None
        body = r.json()
        data = body.get("data", body) if isinstance(body, dict) else {}
        md = (data.get("markdown") or "").strip()
        return md or None
    except Exception:
        return None


def enrich_repo(repo_url: str | None, docs_urls: list[str] | None,
                api_key: str | None = None) -> tuple[list[Chunk], list[dict]]:
    """Scrape candidates → (chunks, sources_meta). Empty when keyless/failing."""
    key = (api_key or settings.firecrawl_api_key or "").strip()
    if not key:
        return [], [{"status": "skipped", "reason": "FIRECRAWL_API_KEY not set"}]
    chunks: list[Chunk] = []
    sources: list[dict] = []
    for url in candidate_urls(repo_url, docs_urls):
        md = firecrawl_scrape(url, key)
        if not md:
            sources.append({"url": url, "status": "failed"})
            continue
        md = md[:MAX_CHARS_PER_SOURCE]
        path = web_path(url)
        for ch in chunk_file(md, path, settings.chunk_lines, settings.chunk_overlap):
            chunks.append(ch)
        sources.append({"url": url, "status": "ok", "path": path,
                        "chars": len(md), "chunks": len(chunks)})
    return chunks, sources
