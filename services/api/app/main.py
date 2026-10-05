"""Sherpa API — FastAPI routes. All answers cite file:line."""
import os
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .agents.mentor import (answer_question, build_overview, build_tour,
                            check_freshness, suggest_starter_tasks)
from .config import settings
from .db import get_session, init_db
from .dbmodels import CustomEndpoint, ProviderKey
from .enrich import enrich_repo
from .ingest import ingest_source
from .models import (AskRequest, FreshnessRequest, IngestRequest, OverviewRequest,
                     TaskRequest, TourRequest)
from .routers import auth as auth_router
from .routers import keys as keys_router
from .security import decrypt_secret, get_optional_user
from .store import RepoStore


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Sherpa — AI Codebase Mentor",
    version="0.4.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# ── CORS ────────────────────────────────────────────────────────────────────
# In production set ALLOWED_ORIGINS env var; falls back to localhost dev URLs.
_raw_origins = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000"
)
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)

app.include_router(auth_router.router)
app.include_router(keys_router.router)

# ── In-memory repo store ─────────────────────────────────────────────────────
_stores: dict[str, RepoStore] = {}

# ── Simple in-process rate limiter ───────────────────────────────────────────
# Tracks (ip, endpoint) request counts per minute. Production deployments should
# replace this with Redis-backed slowapi or a gateway-level rate limiter.
_rate_counts: dict[str, tuple[int, float]] = {}
_RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))


def _check_rate(ip: str, key: str) -> None:
    bucket = f"{ip}:{key}"
    now = time.time()
    count, window_start = _rate_counts.get(bucket, (0, now))
    if now - window_start > 60:
        count, window_start = 0, now
    count += 1
    _rate_counts[bucket] = (count, window_start)
    if count > _RATE_LIMIT:
        raise HTTPException(429, "rate limit exceeded — slow down")


# ── Security headers middleware ───────────────────────────────────────────────
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


# ── Request size guard ────────────────────────────────────────────────────────
MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", str(1 * 1024 * 1024)))  # 1 MB

@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_BYTES:
            raise HTTPException(413, "request body too large")
    return await call_next(request)


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_store(repo_id: str) -> RepoStore:
    if repo_id in _stores:
        return _stores[repo_id]
    path = os.path.join(settings.data_dir, repo_id, "chunks.json")
    if not os.path.exists(path):
        raise HTTPException(404, f"unknown repo_id {repo_id!r}; POST /api/ingest first")
    s = RepoStore(settings.data_dir, repo_id)
    _stores[repo_id] = s
    return s


def _resolve_llm(req: AskRequest, user, db: Session) -> dict:
    """Map the caller's stored credential (key or endpoint) to an LLM override."""
    if req.key_id:
        if user is None:
            raise HTTPException(401, "sign in to use a stored API key")
        k = (
            db.query(ProviderKey)
            .filter(ProviderKey.id == req.key_id, ProviderKey.user_id == user.id)
            .first()
        )
        if not k:
            raise HTTPException(404, "api key not found")
        return {"provider": k.provider, "model": k.model, "api_key": decrypt_secret(k.key_enc)}

    if req.endpoint_id:
        if user is None:
            raise HTTPException(401, "sign in to use a stored endpoint")
        e = (
            db.query(CustomEndpoint)
            .filter(CustomEndpoint.id == req.endpoint_id, CustomEndpoint.user_id == user.id)
            .first()
        )
        if not e:
            raise HTTPException(404, "endpoint not found")
        return {
            "provider": "openai",
            "model": e.model,
            "base_url": e.base_url,
            "api_key": decrypt_secret(e.api_key_enc) if e.api_key_enc else "not-needed",
        }
    return {}


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "ok": True,
        "service": settings.app_name,
        "db": "postgres" if settings.database_url else "sqlite",
        "auth": True,
    }


@app.get("/api/repos")
def repos():
    base = settings.data_dir
    if not os.path.isdir(base):
        return {"repos": []}
    return {
        "repos": [
            d
            for d in os.listdir(base)
            if os.path.exists(os.path.join(base, d, "chunks.json"))
        ]
    }


@app.post("/api/ingest")
def ingest(req: IngestRequest, request: Request):
    _check_rate(request.client.host if request.client else "unknown", "ingest")
    if not req.repo_url and not req.local_path:
        raise HTTPException(422, "provide repo_url or local_path")
    # Basic SSRF guard: only allow public GitHub/GitLab/Bitbucket URLs or explicit local paths
    if req.repo_url:
        allowed_hosts = ("github.com", "gitlab.com", "bitbucket.org")
        from urllib.parse import urlparse
        parsed = urlparse(req.repo_url)
        if parsed.scheme not in ("http", "https"):
            raise HTTPException(422, "repo_url must use http or https")
        if not any(parsed.netloc.endswith(h) for h in allowed_hosts):
            raise HTTPException(422, "only github.com, gitlab.com, and bitbucket.org are supported")
    try:
        repo_id, chunks, meta = ingest_source(req.repo_url, req.local_path, req.branch)
    except Exception as e:
        raise HTTPException(400, f"ingest failed: {e}")
    web_sources: list = []
    if req.enrich_web and (req.repo_url or req.docs_urls):
        web_chunks, web_sources = enrich_repo(req.repo_url, req.docs_urls)
        if web_chunks:
            chunks = chunks + web_chunks
            roles = meta.setdefault("roles", {})
            for c in web_chunks:
                roles.setdefault(c.file, "web docs")
            meta["web_sources"] = web_sources
    store = RepoStore(settings.data_dir, repo_id)
    store.save(chunks, meta)
    _stores[repo_id] = store
    return {
        "repo_id": repo_id,
        "files": len(store.files()),
        "chunks": len(chunks),
        "web_sources": web_sources,
    }


@app.post("/api/ask")
def ask(
    req: AskRequest,
    request: Request,
    user=Depends(get_optional_user),
    db: Session = Depends(get_session),
):
    _check_rate(request.client.host if request.client else "unknown", "ask")
    if not req.question or not req.question.strip():
        raise HTTPException(422, "question must not be empty")
    if len(req.question) > 2000:
        raise HTTPException(422, "question too long (max 2000 chars)")
    return answer_question(
        get_store(req.repo_id),
        req.question.strip(),
        llm_override=_resolve_llm(req, user, db),
    )


@app.post("/api/overview")
def overview(req: OverviewRequest, request: Request):
    _check_rate(request.client.host if request.client else "unknown", "overview")
    return build_overview(get_store(req.repo_id))


@app.post("/api/tours")
def tours(req: TourRequest, request: Request):
    _check_rate(request.client.host if request.client else "unknown", "tours")
    if not req.flow or not req.flow.strip():
        raise HTTPException(422, "flow must not be empty")
    t = build_tour(get_store(req.repo_id), req.flow.strip())
    if not t["steps"]:
        raise HTTPException(404, "no code found for that flow; try different wording")
    return t


@app.post("/api/tasks")
def tasks(req: TaskRequest, request: Request):
    _check_rate(request.client.host if request.client else "unknown", "tasks")
    return suggest_starter_tasks(get_store(req.repo_id), req.level)


@app.post("/api/freshness")
def freshness(req: FreshnessRequest, request: Request):
    _check_rate(request.client.host if request.client else "unknown", "freshness")
    return check_freshness(get_store(req.repo_id), req.docs_markdown)


@app.post("/api/ingest-self")
def ingest_self(request: Request):
    _check_rate(request.client.host if request.client else "unknown", "ingest-self")
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    from .chunk import chunk_file
    from .ingest import _walk, detect_role, repo_id_for

    chunks = []
    roles = {}
    for full in _walk(root):
        rel = os.path.relpath(full, root).replace(os.sep, "/")
        try:
            with open(full, encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        if not text.strip():
            continue
        roles[f"sherpa/{rel}"] = detect_role(rel, text)
        for ch in chunk_file(text, f"sherpa/{rel}", settings.chunk_lines, settings.chunk_overlap):
            chunks.append(ch)
    repo_id = repo_id_for("sherpa-self")
    store = RepoStore(settings.data_dir, repo_id)
    store.save(chunks, {"source": "self", "roles": roles})
    _stores[repo_id] = store
    return {"repo_id": repo_id, "files": len(store.files()), "chunks": len(chunks)}
