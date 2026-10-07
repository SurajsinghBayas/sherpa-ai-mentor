"""Sherpa API — FastAPI routes. All answers cite file:line. CORS open for the demo web app."""
import os
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .agents.mentor import (answer_question, build_overview, build_tour,
                            check_freshness, suggest_starter_tasks)
from .config import settings
from .db import get_session, init_db
from .dbmodels import CustomEndpoint, ProviderKey
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


app = FastAPI(title="Sherpa — AI Codebase Mentor", version="0.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])
app.include_router(auth_router.router)
app.include_router(keys_router.router)

_stores: dict[str, RepoStore] = {}


def get_store(repo_id: str) -> RepoStore:
    if repo_id in _stores:
        return _stores[repo_id]
    path = os.path.join(settings.data_dir, repo_id, "chunks.json")
    if not os.path.exists(path):
        raise HTTPException(404, f"unknown repo_id {repo_id}; POST /api/ingest first")
    s = RepoStore(settings.data_dir, repo_id)
    _stores[repo_id] = s
    return s


def _resolve_llm(req: AskRequest, user, db: Session) -> dict:
    """Map the caller's stored credential (key or endpoint) to an LLM override."""
    if req.key_id:
        if user is None:
            raise HTTPException(401, "sign in to use a stored API key")
        k = db.query(ProviderKey).filter(ProviderKey.id == req.key_id,
                                         ProviderKey.user_id == user.id).first()
        if not k:
            raise HTTPException(404, "api key not found")
        return {"provider": k.provider, "model": k.model,
                "api_key": decrypt_secret(k.key_enc)}
    if req.endpoint_id:
        if user is None:
            raise HTTPException(401, "sign in to use a stored endpoint")
        e = db.query(CustomEndpoint).filter(CustomEndpoint.id == req.endpoint_id,
                                            CustomEndpoint.user_id == user.id).first()
        if not e:
            raise HTTPException(404, "endpoint not found")
        return {"provider": "openai", "model": e.model,
                "base_url": e.base_url,
                "api_key": decrypt_secret(e.api_key_enc) if e.api_key_enc else "not-needed"}
    return {}


@app.get("/health")
def health():
    return {"ok": True, "service": settings.app_name,
            "db": "postgres" if settings.database_url else "sqlite",
            "auth": True}


@app.get("/api/repos")
def repos():
    base = settings.data_dir
    if not os.path.isdir(base):
        return {"repos": []}
    return {"repos": [d for d in os.listdir(base)
                      if os.path.exists(os.path.join(base, d, "chunks.json"))]}


@app.post("/api/ingest")
def ingest(req: IngestRequest):
    if not req.repo_url and not req.local_path:
        raise HTTPException(422, "provide repo_url or local_path")
    try:
        repo_id, chunks, meta = ingest_source(req.repo_url, req.local_path, req.branch)
    except Exception as e:
        raise HTTPException(400, f"ingest failed: {e}")
    store = RepoStore(settings.data_dir, repo_id)
    store.save(chunks, meta)
    _stores[repo_id] = store
    return {"repo_id": repo_id, "files": len(store.files()), "chunks": len(chunks)}


@app.post("/api/ask")
def ask(req: AskRequest, user=Depends(get_optional_user),
        db: Session = Depends(get_session)):
    return answer_question(get_store(req.repo_id), req.question,
                           llm_override=_resolve_llm(req, user, db))


@app.post("/api/overview")
def overview(req: OverviewRequest):
    return build_overview(get_store(req.repo_id))


@app.post("/api/tours")
def tours(req: TourRequest):
    t = build_tour(get_store(req.repo_id), req.flow)
    if not t["steps"]:
        raise HTTPException(404, "no code found for that flow; try different wording")
    return t


@app.post("/api/tasks")
def tasks(req: TaskRequest):
    return suggest_starter_tasks(get_store(req.repo_id), req.level)


@app.post("/api/freshness")
def freshness(req: FreshnessRequest):
    return check_freshness(get_store(req.repo_id), req.docs_markdown)


# self-index endpoint for the demo ("eat your own dogfood")
@app.post("/api/ingest-self")
def ingest_self():
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
