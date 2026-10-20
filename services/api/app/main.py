"""Sherpa API — FastAPI routes. All answers cite file:line."""
import logging
import os
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from .agents.docs import (check_freshness, docs_markdown, generate_docs, get_docs,
                          refresh_docs)
from .agents.mentor import answer_question
from .agents.overview import build_overview
from .agents.tasks import suggest_starter_tasks
from .agents.tour import build_tour
from .config import production_problems, settings
from .db import get_session, init_db
from .dbmodels import CustomEndpoint, ProviderKey, Repo, RepoArtifact, UsageCounter
from .embeddings import embedder
from .ingest import ingest_source, repo_id_for, snapshot_dir, _langs
from .llm import llm
from .models import (AskRequest, DocsRequest, FreshnessRequest, IngestRequest,
                     OverviewRequest, SyncRequest, TaskRequest, TourRequest)
from .routers import auth as auth_router
from .routers import keys as keys_router
from .routers import study as study_router
from .persist import SqlBackend, vectors_supported
from .security import decrypt_secret, get_current_user
from .store import RepoStore

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per HTTP call is noise
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    problems = production_problems(settings)
    if problems:
        raise RuntimeError("unsafe production config: " + "; ".join(problems))
    init_db()
    log.info("startup: env=%s db=%s llm_provider=%s model=%s fallbacks=%s llm_available=%s "
             "embeddings=%s local_ingest=%s", settings.environment,
             "postgres" if settings.database_url else "sqlite", llm.provider, llm.model,
             llm.fallback_models, llm.available,
             embedder.model if embedder.available and vectors_supported() else "off (TF-IDF)",
             settings.allow_local_ingest)
    if not llm.available:
        log.warning("startup: no usable LLM credentials; agents will use offline fallbacks")
    yield


app = FastAPI(title="Sherpa — AI Codebase Mentor", version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs", redoc_url="/api/redoc")

# ── CORS ────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS: list[str] = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
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
app.include_router(study_router.router)

# ── In-memory repo store cache (LRU; reloaded when the DB version moves on) ────
_stores: "OrderedDict[str, RepoStore]" = OrderedDict()
MAX_CACHED_STORES = 16


def _remember(store: RepoStore) -> None:
    _stores[store.repo_id] = store
    _stores.move_to_end(store.repo_id)
    while len(_stores) > MAX_CACHED_STORES:
        _stores.popitem(last=False)

# ── Simple in-process rate limiter ───────────────────────────────────────────
# Tracks (ip, endpoint) request counts per minute. Production deployments should
# replace this with Redis-backed slowapi or a gateway-level rate limiter.
_rate_counts: dict[str, tuple[int, float]] = {}


def _check_rate(request: Request, key: str, user=None) -> None:
    ip = request.client.host if request.client else "unknown"
    bucket = f"{user.id if user else ip}:{key}"
    now = time.time()
    count, window_start = _rate_counts.get(bucket, (0, now))
    if now - window_start > 60:
        count, window_start = 0, now
    count += 1
    _rate_counts[bucket] = (count, window_start)
    if count > settings.rate_limit_per_minute:
        log.warning("rate limit hit ip=%s endpoint=%s", ip, key)
        raise HTTPException(429, "rate limit exceeded — slow down")


# ── Security headers middleware ───────────────────────────────────────────────
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ── Request size guard ────────────────────────────────────────────────────────
@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.max_body_bytes:
            # HTTPException raised in middleware bypasses FastAPI's handlers (→ 500)
            return JSONResponse({"detail": "request body too large"}, status_code=413)
    return await call_next(request)


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_store(repo_id: str, user, db: Session) -> RepoStore:
    """The caller's repo, loaded from the DB (cached until it is re-indexed)."""
    if not repo_id.isalnum():
        raise HTTPException(422, "invalid repo_id")
    row = db.get(Repo, repo_id)
    if row is None or row.owner_id != user.id:  # never reveal other users' repos
        raise HTTPException(404, f"unknown repo_id {repo_id!r}; POST /api/ingest first")
    cached = _stores.get(repo_id)
    if cached is not None and cached.version == row.version:
        _stores.move_to_end(repo_id)
        return cached
    s = RepoStore(repo_id, SqlBackend(repo_id, user.id))
    _remember(s)
    return s


def _charge(db: Session, user, kind: str) -> None:
    """Count one unit of a daily quota (llm | ingest); 429 once it is used up."""
    limit = settings.daily_llm_requests if kind == "llm" else settings.daily_ingests
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = db.get(UsageCounter, (user.id, day, kind))
    if row is None:
        row = UsageCounter(user_id=user.id, day=day, kind=kind, count=0)
        db.add(row)
    if row.count >= limit:
        log.warning("quota: user=%s used all %d %s requests today", user.id, limit, kind)
        raise HTTPException(429, f"daily {kind} limit reached ({limit}); try again tomorrow")
    row.count += 1
    db.commit()


def _resolve_llm(key_id: str | None, endpoint_id: str | None, user, db: Session) -> dict:
    """Map the caller's stored credential (key or endpoint) to an LLM override."""
    if key_id:
        if user is None:
            raise HTTPException(401, "sign in to use a stored API key")
        k = db.query(ProviderKey).filter(ProviderKey.id == key_id,
                                         ProviderKey.user_id == user.id).first()
        if not k:
            raise HTTPException(404, "api key not found")
        return {"provider": k.provider, "model": k.model, "api_key": decrypt_secret(k.key_enc)}
    if endpoint_id:
        if user is None:
            raise HTTPException(401, "sign in to use a stored endpoint")
        e = db.query(CustomEndpoint).filter(CustomEndpoint.id == endpoint_id,
                                            CustomEndpoint.user_id == user.id).first()
        if not e:
            raise HTTPException(404, "endpoint not found")
        return {"provider": "ollama" if e.kind == "ollama" else "openai", "model": e.model,
                "base_url": e.base_url,
                "api_key": decrypt_secret(e.api_key_enc) if e.api_key_enc else "not-needed"}
    return {}


def _validate_source(req: IngestRequest) -> None:
    if not req.repo_url and not req.local_path:
        raise HTTPException(422, "provide repo_url or local_path")
    if req.repo_url:
        parsed = urlparse(req.repo_url.strip())
        if parsed.scheme != "https":
            raise HTTPException(422, "repo_url must be an https:// URL")
        host = (parsed.hostname or "").lower()
        # SSRF guard: public code hosts only (exact host or subdomain)
        if not any(host == h or host.endswith("." + h)
                   for h in ("github.com", "gitlab.com", "bitbucket.org")):
            raise HTTPException(422, "only github.com, gitlab.com, and bitbucket.org are supported")
    elif not settings.allow_local_ingest:
        raise HTTPException(403, "local_path ingest is disabled (set ALLOW_LOCAL_INGEST=true for local dev)")


def _diff(old: dict, new: dict) -> dict:
    return {"added": sorted(set(new) - set(old)),
            "removed": sorted(set(old) - set(new)),
            "modified": sorted(f for f in set(old) & set(new) if old[f] != new[f])}


def _index(repo_url: str | None, local_path: str | None, branch: str, user,
           db: Session) -> tuple[RepoStore, dict]:
    """Ingest a source into the caller's account; if indexed before, report what changed."""
    try:
        _, chunks, meta, sources = ingest_source(repo_url, local_path, branch)
    except Exception as e:  # noqa: BLE001 — surface clone/walk errors to the caller
        log.warning("ingest failed source=%s: %s: %s", repo_url or local_path, type(e).__name__, e)
        raise HTTPException(400, f"ingest failed: {str(e)[:300]}")
    return _save_snapshot(repo_id_for(f"{user.id}:{meta['source']}"), chunks, meta, sources, user, db)


def _save_snapshot(repo_id: str, chunks, meta: dict, sources: dict, user,
                   db: Session) -> tuple[RepoStore, dict]:
    if db.get(Repo, repo_id) is None:
        owned = db.query(Repo).filter(Repo.owner_id == user.id).count()
        if owned >= settings.max_repos_per_user:
            raise HTTPException(429, f"repo limit reached ({settings.max_repos_per_user}); "
                                     "delete one before indexing another")
    store = RepoStore(repo_id, SqlBackend(repo_id, user.id))
    old_hashes = dict(store.meta.get("file_hashes", {}))
    t0 = time.time()
    store.save(chunks, meta, sources)
    changes = _diff(old_hashes, store.meta["file_hashes"]) if old_hashes else {}
    if changes and any(changes.values()):
        store.cache_clear("overview", "tasks")  # docs are kept: they track staleness per section
        log.info("ingest: %s changed — %d added, %d modified, %d removed", repo_id,
                 len(changes["added"]), len(changes["modified"]), len(changes["removed"]))
    _remember(store)
    log.info("ingest ok repo_id=%s files=%d chunks=%d in %.1fs", repo_id, len(store.files()),
             len(chunks), time.time() - t0)
    return store, changes


def _summary(row: Repo, has_docs: bool) -> dict:
    return {"repo_id": row.id, "name": row.name or row.source or row.id, "source": row.source,
            "kind": row.kind, "commit": row.commit, "indexed_at": row.indexed_at,
            "files": row.files_count, "chunks": row.chunks_count,
            "languages": row.languages or [], "has_docs": has_docs}


def _repo_summary(s: RepoStore, db: Session) -> dict:
    db.expire_all()
    return _summary(db.get(Repo, s.repo_id), s.cache_get("docs") is not None)


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"ok": True, "service": settings.app_name,
            "db": "postgres" if settings.database_url else "sqlite", "auth": True,
            "llm": {"provider": llm.provider, "model": llm.model,
                    "fallbacks": llm.fallback_models, "available": llm.available},
            "embeddings": {"model": embedder.model,
                           "available": embedder.available and vectors_supported()},
            "local_ingest": settings.allow_local_ingest}


@app.get("/api/repos")
def repos(user=Depends(get_current_user), db: Session = Depends(get_session)):
    rows = db.query(Repo).filter(Repo.owner_id == user.id).order_by(Repo.indexed_at.desc()).all()
    with_docs = {r for (r,) in db.query(RepoArtifact.repo_id).filter(
        RepoArtifact.name == "docs", RepoArtifact.repo_id.in_([r.id for r in rows]))}
    return {"repos": [_summary(r, r.id in with_docs) for r in rows]}


@app.delete("/api/repos/{repo_id}", status_code=204)
def delete_repo(repo_id: str, user=Depends(get_current_user), db: Session = Depends(get_session)):
    row = db.get(Repo, repo_id)
    if row is None or row.owner_id != user.id:
        raise HTTPException(404, "repo not found")
    db.delete(row)  # files, chunks and artifacts cascade; shared embeddings are kept
    db.commit()
    _stores.pop(repo_id, None)


@app.post("/api/ingest")
def ingest(req: IngestRequest, request: Request, user=Depends(get_current_user),
           db: Session = Depends(get_session)):
    _check_rate(request, "ingest", user)
    _validate_source(req)
    _charge(db, user, "ingest")
    store, changes = _index(req.repo_url and req.repo_url.strip(), req.local_path, req.branch, user, db)
    return {**_repo_summary(store, db), "changes": changes}


@app.post("/api/sync")
def sync(req: SyncRequest, request: Request, user=Depends(get_current_user),
         db: Session = Depends(get_session)):
    """Re-index a repo from its source and refresh any docs sections the change made stale."""
    _check_rate(request, "sync", user)
    old = get_store(req.repo_id, user, db)
    src, kind = old.meta.get("source", ""), old.meta.get("kind")
    if kind == "self":
        raise HTTPException(422, "use /api/ingest-self to re-index Sherpa itself")
    ir = IngestRequest(repo_url=src if kind != "local" and src.startswith("http") else None,
                       local_path=src if kind == "local" or not src.startswith("http") else None,
                       branch=old.meta.get("branch", ""))
    _validate_source(ir)
    _charge(db, user, "ingest")
    store, changes = _index(ir.repo_url, ir.local_path, ir.branch, user, db)
    changed = changes.get("modified", []) + changes.get("removed", []) + changes.get("added", [])
    doc = get_docs(store)
    refreshed = []
    if doc and req.refresh_docs and doc["stale_count"]:
        _charge(db, user, "llm")
        before = {s["id"] for s in doc["sections"] if s["stale"]}
        doc = refresh_docs(store, _resolve_llm(None, None, user, db), changed)
        refreshed = sorted(before)
    return {**_repo_summary(store, db), "changes": changes, "changed_count": len(changed),
            "docs_refreshed": refreshed, "docs": doc}


@app.post("/api/ingest-self")
def ingest_self(request: Request, user=Depends(get_current_user), db: Session = Depends(get_session)):
    """Index Sherpa's own source — a dev convenience, so it follows ALLOW_LOCAL_INGEST."""
    _check_rate(request, "ingest-self", user)
    if not settings.allow_local_ingest:
        raise HTTPException(403, "ingest-self is disabled (set ALLOW_LOCAL_INGEST=true for local dev)")
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    chunks, roles, sources = snapshot_dir(root)
    meta = {"source": "self", "name": "sherpa-ai-mentor (this app)", "kind": "self",
            "indexed_at": time.time(), "roles": roles, "languages": _langs(roles)}
    store, _ = _save_snapshot(repo_id_for(f"{user.id}:sherpa-self"), chunks, meta, sources, user, db)
    return _repo_summary(store, db)


@app.get("/api/file")
def read_file(repo_id: str, path: str, user=Depends(get_current_user),
              db: Session = Depends(get_session)):
    """Full text of one snapshot file, so every citation can be opened and checked."""
    store = get_store(repo_id, user, db)
    real = store.resolve(path)
    if not real:
        raise HTTPException(404, "file not in snapshot")
    lines = store.lines(real)
    return {"path": real, "lines": lines, "total": len(lines),
            "language": real.rsplit(".", 1)[-1].lower() if "." in real else ""}


@app.post("/api/ask")
def ask(req: AskRequest, request: Request, user=Depends(get_current_user),
        db: Session = Depends(get_session)):
    _check_rate(request, "ask", user)
    if not req.question or not req.question.strip():
        raise HTTPException(422, "question must not be empty")
    if len(req.question) > 2000:
        raise HTTPException(422, "question too long (max 2000 chars)")
    store = get_store(req.repo_id, user, db)
    override = _resolve_llm(req.key_id, req.endpoint_id, user, db)
    _charge(db, user, "llm")
    return answer_question(store, req.question.strip(), llm_override=override,
                           history=req.history[-8:])


@app.post("/api/overview")
def overview(req: OverviewRequest, request: Request, user=Depends(get_current_user),
             db: Session = Depends(get_session)):
    _check_rate(request, "overview", user)
    store = get_store(req.repo_id, user, db)
    override = _resolve_llm(req.key_id, req.endpoint_id, user, db)
    if req.refresh or store.cache_get("overview") is None:
        _charge(db, user, "llm")
    return build_overview(store, override, refresh=req.refresh)


@app.post("/api/tours")
def tours(req: TourRequest, request: Request, user=Depends(get_current_user),
          db: Session = Depends(get_session)):
    _check_rate(request, "tours", user)
    if not req.flow or not req.flow.strip():
        raise HTTPException(422, "flow must not be empty")
    if len(req.flow) > 300:
        raise HTTPException(422, "flow too long (max 300 chars)")
    store = get_store(req.repo_id, user, db)
    override = _resolve_llm(req.key_id, req.endpoint_id, user, db)
    _charge(db, user, "llm")
    t = build_tour(store, req.flow.strip(), override)
    if not t["steps"]:
        raise HTTPException(404, "no code found for that flow; try different wording")
    return t


@app.post("/api/tasks")
def tasks(req: TaskRequest, request: Request, user=Depends(get_current_user),
          db: Session = Depends(get_session)):
    _check_rate(request, "tasks", user)
    store = get_store(req.repo_id, user, db)
    override = _resolve_llm(req.key_id, req.endpoint_id, user, db)
    if req.refresh or store.cache_get("tasks") is None:
        _charge(db, user, "llm")
    return suggest_starter_tasks(store, req.level, override, refresh=req.refresh)


@app.get("/api/docs/{repo_id}")
def docs_get(repo_id: str, user=Depends(get_current_user), db: Session = Depends(get_session)):
    doc = get_docs(get_store(repo_id, user, db))
    if not doc:
        raise HTTPException(404, "no docs generated yet; POST /api/docs/generate")
    return doc


@app.get("/api/docs/{repo_id}/markdown", response_class=PlainTextResponse)
def docs_md(repo_id: str, user=Depends(get_current_user), db: Session = Depends(get_session)):
    doc = get_docs(get_store(repo_id, user, db))
    if not doc:
        raise HTTPException(404, "no docs generated yet")
    return docs_markdown(doc)


@app.post("/api/docs/generate")
def docs_generate(req: DocsRequest, request: Request, user=Depends(get_current_user),
                  db: Session = Depends(get_session)):
    _check_rate(request, "docs", user)
    store = get_store(req.repo_id, user, db)
    override = _resolve_llm(req.key_id, req.endpoint_id, user, db)
    _charge(db, user, "llm")
    return generate_docs(store, override)


@app.post("/api/docs/refresh")
def docs_refresh(req: DocsRequest, request: Request, user=Depends(get_current_user),
                 db: Session = Depends(get_session)):
    _check_rate(request, "docs", user)
    store = get_store(req.repo_id, user, db)
    override = _resolve_llm(req.key_id, req.endpoint_id, user, db)
    _charge(db, user, "llm")
    return refresh_docs(store, override)


@app.post("/api/freshness")
def freshness(req: FreshnessRequest, request: Request, user=Depends(get_current_user),
              db: Session = Depends(get_session)):
    _check_rate(request, "freshness", user)
    return check_freshness(get_store(req.repo_id, user, db), req.docs_markdown)
