"""Sherpa API — FastAPI routes. All answers cite file:line."""
import logging
import os
import re
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .agents.docs import (check_freshness, docs_markdown, generate_docs, get_docs,
                          refresh_docs)
from .agents.mentor import answer_question
from .spoken import correct as correct_spoken, vocabulary as spoken_vocabulary
from .agents.overview import build_overview
from .agents.pipeline import build_pipeline
from .agents.city import build_city
from .agents.quiz import build_quiz, grade as grade_quiz
from .agents.tasks import suggest_starter_tasks
from .agents.tour import build_tour
from . import private
from .config import production_problems, production_warnings, settings
from .db import engine as _engine, get_session, init_db
from .guards import check_branch, check_outbound_url, enforce, normalize_repo_url
from .dbmodels import CustomEndpoint, ProviderKey, QuizAttempt, Repo, RepoArtifact, UsageCounter
from .embeddings import embedder
from .ingest import (IngestError, chunk_sources, fetch_source, ingest_source, remote_head,
                     repo_id_for, snapshot_dir, _langs)
from .llm import llm
from .models import (AskRequest, DocsRequest, FreshnessRequest, IngestRequest,
                     OverviewRequest, QuizSubmit, SyncRequest, TaskRequest, TourRequest)
from .routers import auth as auth_router
from .routers import github as github_router
from .routers import profile as profile_router
from .routers import keys as keys_router
from .routers import study as study_router
from .routers import uploads as uploads_router
from .routers import voice as voice_router
from .persist import SqlBackend, vectors_supported
from .security import decrypt_secret, get_current_user
from .store import RepoStore, file_hash

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per HTTP call is noise
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    problems = production_problems(settings)
    if problems:
        raise RuntimeError("unsafe production config: " + "; ".join(problems))
    for w in production_warnings(settings):
        log.warning("startup: %s", w)
    init_db()
    log.info("startup: env=%s db=%s llm_provider=%s model=%s fallbacks=%s llm_available=%s "
             "embeddings=%s local_ingest=%s", settings.environment,
             "postgres" if settings.database_url else "sqlite", llm.provider, llm.model,
             llm.fallback_models, llm.available,
             embedder.model if embedder.available and vectors_supported() else "off (TF-IDF)",
             settings.allow_local_ingest)
    if not llm.available:
        log.warning("startup: no usable LLM credentials; agents will use offline fallbacks")
    private.purge_orphans()  # private code lived in the previous process's memory only
    stop_sweeper = private.start_sweeper()
    yield
    stop_sweeper.set()


# interactive API docs are a dev tool; production doesn't publish its schema
_dev = not settings.is_production
app = FastAPI(title="Sherpa — AI Codebase Mentor", version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs" if _dev else None, redoc_url="/api/redoc" if _dev else None,
              openapi_url="/openapi.json" if _dev else None)

# ── CORS ────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS: list[str] = [
    o.strip() for o in f"{settings.allowed_origins},{settings.desktop_origins}".split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)
_refused_origins: set[str] = set()


@app.middleware("http")
async def log_refused_origin(request: Request, call_next):
    # CORS refusals are silent on this side (the browser just blocks the response), so name the
    # origin once: the fix is adding it to ALLOWED_ORIGINS.
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS and origin not in _refused_origins and len(_refused_origins) < 50:
        _refused_origins.add(origin)
        log.warning("CORS: refused origin %s; add it to ALLOWED_ORIGINS if the web app runs there", origin[:200])
    return await call_next(request)

app.include_router(auth_router.router)
app.include_router(github_router.router)
app.include_router(profile_router.router)
app.include_router(keys_router.router)
app.include_router(study_router.router)
app.include_router(uploads_router.router)
app.include_router(voice_router.router)

# ── In-memory repo store cache (LRU; reloaded when the DB version moves on) ────
_stores: "OrderedDict[str, RepoStore]" = OrderedDict()
_stores_lock = threading.Lock()  # sync routes run on a thread pool
MAX_CACHED_STORES = 16


def _remember(store: RepoStore) -> None:
    with _stores_lock:
        _stores[store.repo_id] = store
        _stores.move_to_end(store.repo_id)
        while len(_stores) > MAX_CACHED_STORES:
            _stores.popitem(last=False)


def _check_rate(request: Request, key: str, user=None) -> None:
    """Per-user (else per-IP) limit of RATE_LIMIT_PER_MINUTE on one endpoint."""
    enforce(request, key, settings.rate_limit_per_minute, 60, who=user.id if user else None)


# ── Ingest concurrency: clones are heavy, so cap them per instance and per user ──
_ingest_slots = threading.BoundedSemaphore(max(1, settings.max_concurrent_ingests))
_ingesting: set[str] = set()
_ingesting_lock = threading.Lock()


class _IngestSlot:
    def __init__(self, user_id: str):
        self.user_id = user_id

    def __enter__(self):
        with _ingesting_lock:
            if self.user_id in _ingesting:
                raise HTTPException(409, "you already have an import running; wait for it to finish")
            _ingesting.add(self.user_id)
        if not _ingest_slots.acquire(timeout=5):
            with _ingesting_lock:
                _ingesting.discard(self.user_id)
            raise HTTPException(503, "the server is busy importing other repositories; try again in a minute",
                                headers={"Retry-After": "30"})
        return self

    def __exit__(self, *_):
        _ingest_slots.release()
        with _ingesting_lock:
            _ingesting.discard(self.user_id)


# ── Request id, access log, and a last-resort error handler ─────────────────────
access_log = logging.getLogger("app.access")


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id", "")[:64] or uuid.uuid4().hex[:16]
    t0 = time.perf_counter()
    try:
        response: Response = await call_next(request)
    except Exception:  # noqa: BLE001 — never leak a traceback to the client
        log.exception("unhandled error rid=%s %s %s", rid, request.method, request.url.path)
        response = JSONResponse({"detail": "internal error; please try again", "request_id": rid},
                                status_code=500)
    ms = (time.perf_counter() - t0) * 1000
    if request.url.path not in ("/health", "/ready"):
        access_log.info("%s %s %d %.0fms rid=%s", request.method, request.url.path,
                        response.status_code, ms, rid)
    response.headers["X-Request-ID"] = rid
    return response


# ── Security headers middleware ───────────────────────────────────────────────
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")  # responses carry private code
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ── Request size guard ────────────────────────────────────────────────────────
class BodyLimit:
    """Reject bodies over MAX_BODY_BYTES, including chunked uploads with no Content-Length."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        # uploaded codebases are the one place a large body is expected
        limit = (settings.max_upload_mb * 1024 * 1024 + 64 * 1024
                 if scope.get("path") == "/api/uploads" else settings.max_body_bytes)
        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None:
            try:
                too_big = int(declared) > limit
            except ValueError:
                return await JSONResponse({"detail": "bad Content-Length"}, status_code=400)(scope, receive, send)
            if too_big:
                return await JSONResponse({"detail": "request body too large"}, status_code=413)(scope, receive, send)
        seen, exceeded, started = 0, False, False

        async def limited():
            nonlocal seen, exceeded
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > limit:  # stop reading; the app sees a disconnect
                    exceeded = True
                    return {"type": "http.disconnect"}
            return msg

        async def guarded_send(msg):
            nonlocal started
            if exceeded and not started:
                return  # drop the app's own error reply; the 413 below replaces it
            started = started or msg["type"] == "http.response.start"
            await send(msg)

        try:
            await self.app(scope, limited, guarded_send)
        except Exception:
            if not exceeded:
                raise
        if exceeded and not started:
            await JSONResponse({"detail": "request body too large"}, status_code=413)(scope, receive, send)


app.add_middleware(BodyLimit)


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_store(repo_id: str, user, db: Session) -> RepoStore:
    """The caller's repo, loaded from the DB (cached until it is re-indexed)."""
    if not repo_id.isalnum():
        raise HTTPException(422, "invalid repo_id")
    row = db.get(Repo, repo_id)
    if row is None or row.owner_id != user.id:  # never reveal other users' repos
        raise HTTPException(404, f"unknown repo_id {repo_id!r}; POST /api/ingest first")
    if row.private:
        s = private.get(repo_id)
        if s is None or row.expires_at < time.time():
            private.end([repo_id], "expired" if s else "not in memory")
            raise HTTPException(410, "this private repo's session ended and its code was wiped; "
                                     "import it again to keep going")
        return s
    with _stores_lock:
        cached = _stores.get(repo_id)
        if cached is not None and cached.version == row.version:
            _stores.move_to_end(repo_id)
            return cached
    s = RepoStore(repo_id, SqlBackend(repo_id, user.id))
    _remember(s)
    return s


def _charge(db: Session, user, kind: str) -> None:
    """Count one unit of a daily quota (llm | ingest); 429 once it is used up.

    The counter row is locked (Postgres) so parallel requests can't both take the last unit.
    """
    limit = settings.daily_llm_requests if kind == "llm" else settings.daily_ingests
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = (user.id, day, kind)
    for attempt in range(2):
        row = db.query(UsageCounter).filter_by(user_id=user.id, day=day, kind=kind) \
            .with_for_update().one_or_none()
        if row is None:
            row = UsageCounter(user_id=user.id, day=day, kind=kind, count=0)
            db.add(row)
        if row.count >= limit:
            db.rollback()
            log.warning("quota: user=%s used all %d %s requests today", user.id, limit, kind)
            raise HTTPException(429, f"daily {kind} limit reached ({limit}); try again tomorrow")
        row.count += 1
        try:
            db.commit()
            return
        except IntegrityError:  # another request created today's row first; count again
            db.rollback()
            if attempt:
                raise
    raise HTTPException(500, f"could not record usage for {key}")


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
        # re-checked at use time: DNS for a saved host can change after it was added
        return {"provider": "ollama" if e.kind == "ollama" else "openai", "model": e.model,
                "base_url": check_outbound_url(e.base_url),
                "api_key": decrypt_secret(e.api_key_enc) if e.api_key_enc else "not-needed"}
    return {}


def _token(req: IngestRequest) -> str:
    """The access token, if any, after a shape check (it goes into an HTTP header)."""
    t = req.token.get_secret_value().strip() if req.token else ""
    if t and (len(t) > 512 or not re.fullmatch(r"[A-Za-z0-9_.\-]+", t)):
        raise HTTPException(422, "that doesn't look like an access token")
    return t


def _validate_source(req: IngestRequest) -> IngestRequest:
    """Normalised copy of the request; public code hosts only (SSRF guard), safe branch name.

    A token means a private repo, so it always turns on private mode."""
    token = _token(req)
    if req.repo_url and req.repo_url.strip():
        return IngestRequest(repo_url=normalize_repo_url(req.repo_url), local_path=None,
                             branch=check_branch(req.branch), private=req.private or bool(token),
                             token=token or None)
    if token:
        raise HTTPException(422, "an access token only applies to a repository URL")
    if not req.local_path:
        raise HTTPException(422, "provide repo_url or local_path")
    if not settings.allow_local_ingest:
        raise HTTPException(403, "local_path ingest is disabled (set ALLOW_LOCAL_INGEST=true for local dev)")
    return req


def _diff(old: dict, new: dict) -> dict:
    return {"added": sorted(set(new) - set(old)),
            "removed": sorted(set(old) - set(new)),
            "modified": sorted(f for f in set(old) & set(new) if old[f] != new[f])}


def _index(repo_url: str | None, local_path: str | None, branch: str, user,
           db: Session, is_private: bool = False, token: str = "") -> tuple[RepoStore, dict]:
    """Ingest a source into the caller's account; if indexed before, report what changed."""
    with _IngestSlot(user.id):
        try:
            _, chunks, meta, sources = ingest_source(repo_url, local_path, branch, token)
        except (IngestError, ValueError) as e:  # messages written for the user
            log.warning("ingest failed source=%s: %s", repo_url or local_path, e)
            raise HTTPException(400, f"ingest failed: {str(e)[:300]}")
        except Exception:  # noqa: BLE001 — unexpected: log it, don't leak internals
            log.exception("ingest crashed source=%s", repo_url or local_path)
            raise HTTPException(500, "ingest failed unexpectedly; please try again")
    if is_private:
        return _save_private(repo_id_for(f"{user.id}:private:{meta['source']}"), chunks, meta,
                             sources, user, db)
    return _save_snapshot(repo_id_for(f"{user.id}:{meta['source']}"), chunks, meta, sources, user, db)


def _check_repo_limit(repo_id: str, user, db: Session) -> None:
    if db.get(Repo, repo_id) is None:
        owned = db.query(Repo).filter(Repo.owner_id == user.id).count()
        if owned >= settings.max_repos_per_user:
            raise HTTPException(429, f"repo limit reached ({settings.max_repos_per_user}); "
                                     "delete one before indexing another")


def _save_private(repo_id: str, chunks, meta: dict, sources: dict, user,
                  db: Session) -> tuple[RepoStore, dict]:
    """Private mode: the snapshot is held in memory only (see app/private.py)."""
    _check_repo_limit(repo_id, user, db)
    if private.get(repo_id) is None and private.count() >= settings.max_private_repos:
        raise HTTPException(503, "the server is holding as many private repos as it can; "
                                 "try again later")
    t0 = time.time()
    store = private.new_store(repo_id, user.id)
    store.save(chunks, meta, sources)
    private.put(store)
    log.info("ingest ok (private, memory only) repo_id=%s files=%d chunks=%d in %.1fs", repo_id,
             len(store.files()), len(chunks), time.time() - t0)
    return store, {}


def _save_snapshot(repo_id: str, chunks, meta: dict, sources: dict, user,
                   db: Session) -> tuple[RepoStore, dict]:
    _check_repo_limit(repo_id, user, db)
    store = RepoStore(repo_id, SqlBackend(repo_id, user.id))
    old_hashes = dict(store.meta.get("file_hashes", {}))
    t0 = time.time()
    store.save(chunks, meta, sources)
    changes = _diff(old_hashes, store.meta["file_hashes"]) if old_hashes else {}
    if changes and any(changes.values()):
        store.cache_clear("overview", "tasks", "pipeline", "city", "quiz")  # docs are kept: they track staleness per section
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
            "languages": row.languages or [], "has_docs": has_docs,
            "private": bool(row.private), "expires_at": row.expires_at if row.private else None}


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
            "local_ingest": settings.allow_local_ingest,
            "private_ttl_hours": settings.private_ttl_hours}


# The CLI is one stdlib-only file; serving it here means anyone signed in to this
# deployment can install it without access to the source repository.
CLI_PATH = os.path.join(os.path.dirname(__file__), "static", "sherpa_cli.py")


@app.get("/cli/sherpa.py", response_class=PlainTextResponse)
def download_cli(request: Request):
    """The `sherpa` CLI, preset to talk to the API it was downloaded from."""
    try:
        with open(CLI_PATH, encoding="utf-8") as f:
            src = f.read()
    except OSError:
        raise HTTPException(404, "CLI not bundled with this server")
    base = str(request.base_url).rstrip("/")  # https behind the proxy thanks to --proxy-headers
    src = src.replace('DEFAULT_API = "http://localhost:8000"', f"DEFAULT_API = {base!r}", 1)
    return PlainTextResponse(src, media_type="text/x-python; charset=utf-8",
                             headers={"Cache-Control": "public, max-age=300",
                                      "Content-Disposition": 'inline; filename="sherpa"'})


@app.get("/ready")
def ready():
    """Readiness for the load balancer: 503 until the database answers."""
    try:
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        log.error("ready: database unreachable: %s", type(e).__name__)
        return JSONResponse({"ok": False, "db": "unreachable"}, status_code=503)
    return {"ok": True}


@app.get("/api/repos")
def repos(user=Depends(get_current_user), db: Session = Depends(get_session)):
    rows = db.query(Repo).filter(Repo.owner_id == user.id).order_by(Repo.indexed_at.desc()).all()
    # private repos whose time is up (or whose memory is gone) are wiped before listing
    ended = [r.id for r in rows if r.private and
             (r.expires_at < time.time() or private.get(r.id) is None)]
    if ended:
        private.end(ended, "expired")
        rows = [r for r in rows if r.id not in ended]
    with_docs = {r for (r,) in db.query(RepoArtifact.repo_id).filter(
        RepoArtifact.name == "docs", RepoArtifact.repo_id.in_([r.id for r in rows]))}
    with_docs |= {r.id for r in rows if r.private and private.get(r.id).cache_get("docs")}
    return {"repos": [_summary(r, r.id in with_docs) for r in rows]}


@app.delete("/api/repos/{repo_id}", status_code=204)
def delete_repo(repo_id: str, user=Depends(get_current_user), db: Session = Depends(get_session)):
    row = db.get(Repo, repo_id)
    if row is None or row.owner_id != user.id:
        raise HTTPException(404, "repo not found")
    db.delete(row)  # files, chunks and artifacts cascade; shared embeddings are kept
    db.commit()
    private.drop(repo_id)  # a private repo's code and vectors go with it
    with _stores_lock:
        _stores.pop(repo_id, None)
    _last_check.pop(repo_id, None)


@app.post("/api/ingest")
def ingest(req: IngestRequest, request: Request, user=Depends(get_current_user),
           db: Session = Depends(get_session)):
    _check_rate(request, "ingest", user)
    req = _validate_source(req)
    _charge(db, user, "ingest")
    store, changes = _index(req.repo_url, req.local_path, req.branch, user, db,
                            is_private=req.private, token=_token(req))
    return {**_repo_summary(store, db), "changes": changes}


def _source_of(store: RepoStore) -> IngestRequest:
    """Where a repo was indexed from, re-validated (the rules may have tightened since)."""
    src, kind = store.meta.get("source", ""), store.meta.get("kind")
    if kind == "self":
        raise HTTPException(422, "use /api/ingest-self to re-index Sherpa itself")
    if kind == "upload":
        raise HTTPException(422, "this project was uploaded; upload it again to update it "
                                 "(only changed files are re-indexed)")
    is_git = kind != "local" and src.startswith("http")
    return _validate_source(IngestRequest(repo_url=src if is_git else None,
                                          local_path=None if is_git else src,
                                          branch=store.meta.get("branch", "")))


def _reindex(old: RepoStore, user, db: Session, full: bool) -> tuple[RepoStore, dict]:
    """Re-read a repo from its source into the SAME repo_id.

    full=False: only added/modified/removed files are re-chunked, re-embedded and rewritten.
    full=True:  the whole index is rebuilt from scratch (manual "Reindex").
    """
    src = _source_of(old)
    with _IngestSlot(user.id):
        try:
            sources, meta = fetch_source(src.repo_url, src.local_path, src.branch)
        except (IngestError, ValueError) as e:
            log.warning("reindex failed repo=%s: %s", old.repo_id, e)
            raise HTTPException(400, f"reindex failed: {str(e)[:300]}")
        except Exception:  # noqa: BLE001
            log.exception("reindex crashed repo=%s", old.repo_id)
            raise HTTPException(500, "reindex failed unexpectedly; please try again")
    meta["source"] = old.meta.get("source", meta["source"])  # keep the stored identity
    old_hashes = dict(old.meta.get("file_hashes") or {})
    new_hashes = {p: file_hash(t) for p, t in sources.items()}
    changes = _diff(old_hashes, new_hashes) if old_hashes else \
        {"added": sorted(sources), "removed": [], "modified": []}
    t0 = time.time()
    if full or not old_hashes:
        chunks = chunk_sources(sources)
        if not chunks:
            raise HTTPException(400, "reindex failed: no readable source files found")
        store = RepoStore(old.repo_id, SqlBackend(old.repo_id, user.id))
        store.save(chunks, meta, sources)
        store.cache_clear("overview", "tasks", "pipeline", "city", "quiz")  # a manual rebuild starts the analyses fresh
        mode = "full"
    else:
        store = RepoStore(old.repo_id, SqlBackend(old.repo_id, user.id))
        new_chunks = chunk_sources(sources, only=set(changes["added"]) | set(changes["modified"]))
        store.apply_changes(sources, meta, changes, new_chunks)
        if any(changes.values()):
            store.cache_clear("overview", "tasks", "pipeline", "city", "quiz")  # docs keep their per-section staleness
        mode = "incremental"
    _remember(store)
    n = sum(len(v) for v in changes.values())
    log.info("reindex %s repo=%s: %d files changed (%d added, %d modified, %d removed) in %.1fs",
             mode, old.repo_id, n, len(changes["added"]), len(changes["modified"]),
             len(changes["removed"]), time.time() - t0)
    return store, changes


# last automatic check per repo: (monotonic time, latest remote commit)
_last_check: dict[str, tuple[float, str]] = {}
CHECK_INTERVAL = 60


@app.post("/api/repos/{repo_id}/check")
def check_for_updates(repo_id: str, request: Request, user=Depends(get_current_user),
                      db: Session = Depends(get_session)):
    """Automatic re-index: compare the remote's latest commit with the indexed one, and if
    it moved, re-index only the files that changed. Cheap when nothing changed (one
    `git ls-remote`, no clone, no quota)."""
    _check_rate(request, "check", user)
    old = get_store(repo_id, user, db)
    kind, current = old.meta.get("kind"), old.meta.get("commit") or ""
    # no remote to compare with (uploads update by re-uploading); private repos keep no token
    if kind in ("self", "upload") or isinstance(old.backend, private.PrivateBackend):
        return {"status": "unsupported", "commit": current}
    src = _source_of(old)
    if src.repo_url:
        now = time.monotonic()
        cached = _last_check.get(repo_id)
        if cached and now - cached[0] < CHECK_INTERVAL:
            latest = cached[1]
        else:
            try:
                latest = remote_head(src.repo_url, src.branch)
            except IngestError as e:
                return {"status": "error", "detail": str(e), "commit": current}
            _last_check[repo_id] = (now, latest)
        # older snapshots stored a short sha
        if current and latest.startswith(current):
            return {"status": "up_to_date", "commit": current, "latest": latest}
    else:  # local folder (dev only): no commit to compare, so compare file hashes
        latest = ""
        try:
            sources, _ = fetch_source(None, src.local_path)
        except (IngestError, ValueError) as e:
            return {"status": "error", "detail": str(e), "commit": current}
        if {p: file_hash(t) for p, t in sources.items()} == old.meta.get("file_hashes"):
            return {"status": "up_to_date", "commit": current, "latest": latest}
    try:
        _charge(db, user, "ingest")
        store, changes = _reindex(old, user, db, full=False)
    except HTTPException as e:
        if e.status_code in (409, 429, 503):  # busy or out of quota: say so, don't fail the page
            return {"status": "outdated", "detail": e.detail, "commit": current, "latest": latest}
        raise
    if src.repo_url:
        _last_check[repo_id] = (time.monotonic(), store.meta.get("commit") or latest)
    return {"status": "updated", **_repo_summary(store, db), "previous_commit": current,
            "changes": changes, "changed_count": sum(len(v) for v in changes.values())}


@app.post("/api/sync")
def sync(req: SyncRequest, request: Request, user=Depends(get_current_user),
         db: Session = Depends(get_session)):
    """Re-index a repo from its source (incremental, or `full` for a manual rebuild) and
    refresh any docs sections the change made stale."""
    _check_rate(request, "sync", user)
    old = get_store(req.repo_id, user, db)
    if isinstance(old.backend, private.PrivateBackend):
        raise HTTPException(422, "private repos aren't synced, because no token is kept; "
                                 "import it again to pick up changes")
    _source_of(old)  # validate before spending quota
    _charge(db, user, "ingest")
    store, changes = _reindex(old, user, db, full=req.full)
    _last_check.pop(req.repo_id, None)
    changed = changes.get("modified", []) + changes.get("removed", []) + changes.get("added", [])
    doc = get_docs(store)
    refreshed = []
    if doc and req.refresh_docs and doc["stale_count"]:
        _charge(db, user, "llm")
        before = {s["id"] for s in doc["sections"] if s["stale"]}
        doc = refresh_docs(store, _resolve_llm(None, None, user, db), changed)
        refreshed = sorted(before)
    return {**_repo_summary(store, db), "changes": changes, "changed_count": len(changed),
            "full": req.full, "docs_refreshed": refreshed, "docs": doc}


@app.post("/api/ingest-self")
def ingest_self(request: Request, user=Depends(get_current_user), db: Session = Depends(get_session)):
    """Index Sherpa's own source — a dev convenience, so it follows ALLOW_LOCAL_INGEST."""
    _check_rate(request, "ingest-self", user)
    if not settings.allow_local_ingest:
        raise HTTPException(403, "ingest-self is disabled (set ALLOW_LOCAL_INGEST=true for local dev)")
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    with _IngestSlot(user.id):
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
    question = req.question.strip()
    if req.spoken:  # heard, not typed: "deps dot py" → deps.py, using this repo's own names
        question = correct_spoken(question, spoken_vocabulary(store))
    return answer_question(store, question, llm_override=override,
                           history=req.history[-8:], spoken=req.spoken)


@app.post("/api/overview")
def overview(req: OverviewRequest, request: Request, user=Depends(get_current_user),
             db: Session = Depends(get_session)):
    _check_rate(request, "overview", user)
    store = get_store(req.repo_id, user, db)
    override = _resolve_llm(req.key_id, req.endpoint_id, user, db)
    if req.refresh or store.cache_get("overview") is None:
        _charge(db, user, "llm")
    return build_overview(store, override, refresh=req.refresh)


@app.post("/api/pipeline")
def pipeline(req: OverviewRequest, request: Request, user=Depends(get_current_user),
             db: Session = Depends(get_session)):
    """How the repo's agent loop, ML pipeline or workflow runs, stage by stage (drawn as a machine)."""
    _check_rate(request, "pipeline", user)
    store = get_store(req.repo_id, user, db)
    override = _resolve_llm(req.key_id, req.endpoint_id, user, db)
    if req.refresh or store.cache_get("pipeline") is None:
        _charge(db, user, "llm")
    return build_pipeline(store, override, refresh=req.refresh)


@app.post("/api/city")
def city(req: OverviewRequest, request: Request, user=Depends(get_current_user),
         db: Session = Depends(get_session)):
    """The codebase as a city (districts = components, buildings = files) and how it grew."""
    _check_rate(request, "city", user)
    store = get_store(req.repo_id, user, db)
    return build_city(store, refresh=req.refresh)


@app.post("/api/quiz")
def quiz(req: OverviewRequest, request: Request, user=Depends(get_current_user),
         db: Session = Depends(get_session)):
    """The latest skill check for this repo, or new questions (`refresh`). Answers stay on the server."""
    _check_rate(request, "quiz", user)
    store = get_store(req.repo_id, user, db)
    override = _resolve_llm(req.key_id, req.endpoint_id, user, db)
    saved = store.cache_get("quiz") or {}
    if req.refresh or saved.get("snapshot") != store.snapshot_hash or not saved.get("order"):
        _charge(db, user, "llm")
    return build_quiz(store, override, fresh=req.refresh)


@app.post("/api/quiz/submit")
def quiz_submit(req: QuizSubmit, request: Request, user=Depends(get_current_user),
                db: Session = Depends(get_session)):
    _check_rate(request, "quiz", user)
    store = get_store(req.repo_id, user, db)
    result = grade_quiz(store, req.quiz_id, req.answers)
    if result is None:
        raise HTTPException(409, "this quiz is out of date (the repo was re-indexed); start a new one")
    row = QuizAttempt(user_id=user.id, repo_id=req.repo_id, quiz_id=req.quiz_id, correct=result["correct"],
                      total=result["total"], seconds=req.seconds,
                      areas=[{k: x[k] for k in ("key", "name", "correct", "total")} for x in result["areas"]])
    db.add(row)
    db.commit()
    return result


@app.get("/api/quiz/attempts")
def quiz_attempts(repo_id: str, request: Request, user=Depends(get_current_user),
                  db: Session = Depends(get_session)):
    get_store(repo_id, user, db)  # the caller's own repo only
    rows = db.query(QuizAttempt).filter(QuizAttempt.user_id == user.id, QuizAttempt.repo_id == repo_id) \
        .order_by(QuizAttempt.created_at.desc()).limit(10).all()
    return {"attempts": [{"id": r.id, "correct": r.correct, "total": r.total, "seconds": r.seconds,
                          "areas": r.areas or [], "at": r.created_at.timestamp() if r.created_at else 0}
                         for r in rows]}


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
