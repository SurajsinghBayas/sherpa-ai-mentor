"""Private mode: a repo whose code never reaches the database or disk.

Its files, chunks, embedding vectors and generated outputs (overview, tours, docs) live
only in this process's memory. The database keeps one `repos` row (name, source URL,
counts, languages, expiry) so the dashboard can list it. The snapshot is wiped when the
user deletes it, when it expires (PRIVATE_TTL_HOURS), or when the server restarts.

Because the data is per-process, private mode assumes one API instance (or sticky
sessions). Embeddings come from Bedrock, which doesn't store or train on inputs.
"""
import logging
import threading
import time
from typing import Dict, List, Optional

import numpy as np
from sqlalchemy import delete, select

from . import db as dbmod
from .chunk import Chunk
from .config import settings
from .dbmodels import Repo
from .embeddings import embedder
from .persist import SqlBackend, embed_input
from .store import RepoStore

log = logging.getLogger(__name__)

_live: Dict[str, RepoStore] = {}
_lock = threading.Lock()


class PrivateBackend:
    """RepoStore backend that keeps everything in memory; only the summary row is in SQL."""

    def __init__(self, repo_id: str, owner_id: str):
        self.repo_id = repo_id
        self.owner_id = owner_id
        self.artifacts: Dict[str, Dict] = {}
        self.vectors: Optional[np.ndarray] = None  # unit-length rows, one per chunk
        self.on_progress = None

    def load(self):
        return None  # nothing to load: a private snapshot only exists in the store that built it

    def save(self, chunks: List[Chunk], meta: Dict, sources: Dict[str, str]) -> int:
        # Same summary columns as a normal repo, but `meta` (file paths, roles, hashes) stays here.
        summary = {k: meta.get(k) for k in ("source", "name", "kind", "branch", "commit",
                                             "indexed_at", "languages")}
        with dbmod.SessionLocal() as db:
            repo = SqlBackend(self.repo_id, self.owner_id)._update_repo(
                db, summary, len(sources) or len({c.file for c in chunks}), len(chunks))
            repo.meta = {}
            repo.private = True
            repo.expires_at = time.time() + settings.private_ttl_hours * 3600
            version = repo.version
            db.commit()
        self.artifacts.clear()
        self._embed(chunks)
        return version

    def save_incremental(self, *_args, **_kwargs) -> int:
        raise NotImplementedError("private repos are re-imported, not updated in place")

    def _embed(self, chunks: List[Chunk]) -> None:
        self.vectors = None
        if not embedder.available or not chunks:
            return  # keyword + TF-IDF search still works
        try:
            report = (lambda d, t: self.on_progress("embedding", d, t)) if self.on_progress else None
            vecs = np.asarray(embedder.embed_documents([embed_input(c) for c in chunks],
                                                       on_progress=report), dtype=np.float32)
        except Exception as e:  # noqa: BLE001
            log.warning("private repo %s: embeddings failed (%s); TF-IDF search only",
                        self.repo_id, e)
            return
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        self.vectors = vecs / np.where(norms == 0, 1, norms)

    def cache_get(self, name: str) -> Dict | None:
        return self.artifacts.get(name)

    def cache_put(self, name: str, value: Dict) -> None:
        self.artifacts[name] = value

    def cache_clear(self, *names: str) -> None:
        for n in names:
            self.artifacts.pop(n, None)

    def vector_scores(self, query: str, n: int) -> Optional[Dict[int, float]]:
        if self.vectors is None:
            return None
        qv = embedder.embed_query(query)
        if qv is None:
            return None
        q = np.asarray(qv, dtype=np.float32)
        sims = self.vectors @ (q / (np.linalg.norm(q) or 1))
        top = np.argsort(-sims)[:n]
        return {int(i): max(0.0, float(sims[i])) for i in top}


# ── registry ──────────────────────────────────────────────────────────────────

def new_store(repo_id: str, owner_id: str) -> RepoStore:
    return RepoStore(repo_id, PrivateBackend(repo_id, owner_id))


def put(store: RepoStore) -> None:
    with _lock:
        _live[store.repo_id] = store


def get(repo_id: str) -> Optional[RepoStore]:
    with _lock:
        return _live.get(repo_id)


def drop(repo_id: str) -> None:
    with _lock:
        _live.pop(repo_id, None)


def count() -> int:
    with _lock:
        return len(_live)


def end(repo_ids: List[str], why: str) -> None:
    """Wipe these private repos from memory and delete their summary rows."""
    if not repo_ids:
        return
    with _lock:
        for r in repo_ids:
            _live.pop(r, None)
    with dbmod.SessionLocal() as db:
        db.execute(delete(Repo).where(Repo.id.in_(repo_ids), Repo.private.is_(True)))
        db.commit()
    log.info("private: ended %d repo(s) (%s)", len(repo_ids), why)


def purge_expired() -> None:
    with dbmod.SessionLocal() as db:
        ids = list(db.execute(select(Repo.id).where(Repo.private.is_(True),
                                                    Repo.expires_at < time.time())).scalars())
    end(ids, "expired")


def purge_orphans() -> None:
    """At startup: any private row is from a previous process, so its code is already gone."""
    with dbmod.SessionLocal() as db:
        ids = list(db.execute(select(Repo.id).where(Repo.private.is_(True))).scalars())
    end([i for i in ids if get(i) is None], "server restarted")


def start_sweeper(interval: float = 60) -> threading.Event:
    """Background thread that wipes expired private repos; set the returned event to stop it."""
    stop = threading.Event()

    def loop():
        while not stop.wait(interval):
            try:
                purge_expired()
            except Exception:  # noqa: BLE001 — a DB blip must not kill the sweeper
                log.exception("private: sweep failed")

    threading.Thread(target=loop, name="private-sweeper", daemon=True).start()
    return stop
