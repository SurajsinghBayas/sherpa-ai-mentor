"""Sherpa API — FastAPI routes. All answers cite file:line. CORS open for the demo web app."""
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .agents.mentor import (answer_question, build_overview, build_tour,
                            check_freshness, suggest_starter_tasks)
from .config import settings
from .ingest import ingest_source
from .models import (AskRequest, FreshnessRequest, IngestRequest, OverviewRequest,
                     TaskRequest, TourRequest)
from .store import RepoStore

app = FastAPI(title="Sherpa — AI Codebase Mentor", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

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


@app.get("/health")
def health():
    return {"ok": True, "service": settings.app_name}


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
def ask(req: AskRequest):
    return answer_question(get_store(req.repo_id), req.question)


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
