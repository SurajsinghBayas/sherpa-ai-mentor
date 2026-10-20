"""SQL persistence for repo snapshots, plus pgvector search on Postgres.

Tables come from dbmodels (portable across SQLite and Postgres). Embeddings live in
`chunk_embeddings` (Postgres only, migration 0002), keyed by (model, text_hash), so a
chunk that hasn't changed is never embedded twice — across re-indexes and users.
"""
import hashlib
import logging
import time
from typing import Dict, List, Optional

from sqlalchemy import delete, func, insert, select, text

from . import db as dbmod
from .chunk import Chunk
from .dbmodels import Repo, RepoArtifact, RepoChunk, RepoFile
from .embeddings import embedder
from .store import file_hash

log = logging.getLogger(__name__)

BATCH = 500


def embed_input(c: Chunk) -> str:
    return f"{c.file}\n{c.text}"


def text_hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest()


def vectors_supported() -> bool:
    return dbmod.engine.dialect.name == "postgresql"


def _vec_literal(v: List[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


class SqlBackend:
    def __init__(self, repo_id: str, owner_id: str | None = None):
        self.repo_id = repo_id
        self.owner_id = owner_id
        # repo_chunks.ord of each loaded chunk, in list order. Incremental re-indexes leave
        # gaps (removed files) and append new ords, so ord is not the list index.
        self._ord_index: Dict[int, int] = {}

    # ---------- snapshot ----------

    def load(self):
        with dbmod.SessionLocal() as db:
            repo = db.get(Repo, self.repo_id)
            if repo is None or not repo.version:
                return None
            rows = db.execute(select(RepoChunk.ord, RepoChunk.file, RepoChunk.start_line,
                                     RepoChunk.end_line, RepoChunk.text, RepoChunk.kind)
                              .where(RepoChunk.repo_id == self.repo_id)
                              .order_by(RepoChunk.ord)).all()
            chunks = [Chunk(file=f, start_line=s, end_line=e, text=t, kind=k)
                      for _, f, s, e, t, k in rows]
            self._ord_index = {o: i for i, (o, *_rest) in enumerate(rows)}
            sources = dict(db.execute(select(RepoFile.path, RepoFile.text)
                                      .where(RepoFile.repo_id == self.repo_id)).all())
            meta = dict(repo.meta or {})
            meta.update(source=repo.source, name=repo.name, kind=repo.kind, branch=repo.branch,
                        commit=repo.commit, indexed_at=repo.indexed_at, languages=repo.languages)
            return chunks, meta, sources, repo.version

    def _update_repo(self, db, meta: Dict, files_count: int, chunks_count: int) -> Repo:
        core = ("source", "name", "kind", "branch", "commit", "indexed_at", "languages")
        repo = db.get(Repo, self.repo_id)
        if repo is None:
            if not self.owner_id:
                raise ValueError("a new repo needs an owner")
            repo = Repo(id=self.repo_id, owner_id=self.owner_id, version=0)
            db.add(repo)
        repo.name = str(meta.get("name") or meta.get("source") or "")[:300]
        repo.source = str(meta.get("source", ""))[:1000]
        repo.kind = str(meta.get("kind", "git"))[:16]
        repo.branch = str(meta.get("branch") or "")[:200]
        repo.commit = str(meta.get("commit") or "")[:64]
        repo.indexed_at = float(meta.get("indexed_at") or time.time())
        repo.languages = list(meta.get("languages") or [])
        repo.meta = {k: v for k, v in meta.items() if k not in core}
        repo.files_count = files_count
        repo.chunks_count = chunks_count
        repo.version = (repo.version or 0) + 1
        db.flush()
        return repo

    def _insert(self, db, chunks: List[Chunk], hashes: List[str], first_ord: int,
                sources: Dict[str, str]) -> None:
        rows = [{"repo_id": self.repo_id, "ord": first_ord + i, "file": c.file,
                 "start_line": c.start_line, "end_line": c.end_line, "kind": c.kind,
                 "text": c.text, "text_hash": h}
                for i, (c, h) in enumerate(zip(chunks, hashes))]
        for i in range(0, len(rows), BATCH):
            db.execute(insert(RepoChunk), rows[i:i + BATCH])
        frows = [{"repo_id": self.repo_id, "path": p, "hash": file_hash(t), "text": t}
                 for p, t in sources.items()]
        for i in range(0, len(frows), BATCH):
            db.execute(insert(RepoFile), frows[i:i + BATCH])

    def save(self, chunks: List[Chunk], meta: Dict, sources: Dict[str, str]) -> int:
        """Replace the whole snapshot (first index, or a manual full re-index)."""
        hashes = [text_hash(embed_input(c)) for c in chunks]
        with dbmod.SessionLocal() as db:
            repo = self._update_repo(db, meta, len(sources) or len({c.file for c in chunks}),
                                     len(chunks))
            db.execute(delete(RepoChunk).where(RepoChunk.repo_id == self.repo_id))
            db.execute(delete(RepoFile).where(RepoFile.repo_id == self.repo_id))
            self._insert(db, chunks, hashes, 0, sources)
            version = repo.version
            db.commit()
        self._ord_index = {i: i for i in range(len(chunks))}
        self._ensure_embeddings(chunks, hashes)
        return version

    def save_incremental(self, changed: Dict[str, str], removed: List[str],
                         new_chunks: List[Chunk], meta: Dict, files_count: int,
                         chunks_count: int) -> int:
        """Rewrite only the rows of changed/added/removed files; everything else stays put.

        `changed` maps each added or modified path to its new text; `new_chunks` are the
        chunks of exactly those files. Callers reload afterwards (ords are appended).
        """
        hashes = [text_hash(embed_input(c)) for c in new_chunks]
        touched = list(changed) + list(removed)
        with dbmod.SessionLocal() as db:
            repo = self._update_repo(db, meta, files_count, chunks_count)
            for i in range(0, len(touched), BATCH):
                part = touched[i:i + BATCH]
                db.execute(delete(RepoChunk).where(RepoChunk.repo_id == self.repo_id,
                                                   RepoChunk.file.in_(part)))
                db.execute(delete(RepoFile).where(RepoFile.repo_id == self.repo_id,
                                                  RepoFile.path.in_(part)))
            top = db.execute(select(func.max(RepoChunk.ord))
                             .where(RepoChunk.repo_id == self.repo_id)).scalar()
            self._insert(db, new_chunks, hashes, (top if top is not None else -1) + 1, changed)
            version = repo.version
            db.commit()
        self._ensure_embeddings(new_chunks, hashes)
        return version

    # ---------- embeddings ----------

    def _ensure_embeddings(self, chunks: List[Chunk], hashes: List[str]) -> None:
        if not vectors_supported():
            return
        if not embedder.available:
            log.warning("embeddings: AWS_BEARER_TOKEN_BEDROCK not set; repo %s searchable by "
                        "TF-IDF only (FALLBACK)", self.repo_id)
            return
        todo: Dict[str, str] = {}
        with dbmod.engine.connect() as conn:
            have = set()
            uniq = sorted(set(hashes))
            for i in range(0, len(uniq), BATCH):
                have |= set(conn.execute(
                    text("SELECT text_hash FROM chunk_embeddings WHERE model = :m "
                         "AND text_hash = ANY(:h)"),
                    {"m": embedder.model, "h": uniq[i:i + BATCH]}).scalars())
        for c, h in zip(chunks, hashes):
            if h not in have:
                todo.setdefault(h, embed_input(c))
        if not todo:
            log.info("embeddings: repo %s — all %d chunks already embedded", self.repo_id, len(chunks))
            return
        t0 = time.time()
        items = list(todo.items())
        try:
            vectors = embedder.embed_documents([t for _, t in items])
        except Exception as e:  # noqa: BLE001
            log.warning("embeddings: failed for repo %s (%s); FALLBACK to TF-IDF search",
                        self.repo_id, e)
            return
        with dbmod.engine.begin() as conn:
            for i in range(0, len(items), BATCH):
                conn.execute(
                    text("INSERT INTO chunk_embeddings (model, text_hash, embedding) "
                         "VALUES (:m, :h, CAST(:v AS vector)) ON CONFLICT DO NOTHING"),
                    [{"m": embedder.model, "h": h, "v": _vec_literal(v)}
                     for (h, _), v in zip(items[i:i + BATCH], vectors[i:i + BATCH])])
        log.info("embeddings: repo %s — embedded %d new chunks (%d reused) in %.1fs",
                 self.repo_id, len(items), len(chunks) - len(items), time.time() - t0)

    def vector_scores(self, query: str, n: int) -> Optional[Dict[int, float]]:
        """Cosine similarity of the query to the top-n chunks (exact scan within one repo)."""
        if not vectors_supported():
            return None
        qv = embedder.embed_query(query)
        if qv is None:
            return None
        try:
            with dbmod.engine.connect() as conn:
                rows = conn.execute(text(
                    "SELECT c.ord, 1 - (e.embedding <=> CAST(:q AS vector)) AS sim "
                    "FROM repo_chunks c JOIN chunk_embeddings e "
                    "ON e.model = :m AND e.text_hash = c.text_hash "
                    "WHERE c.repo_id = :r ORDER BY e.embedding <=> CAST(:q AS vector) LIMIT :n"),
                    {"q": _vec_literal(qv), "m": embedder.model, "r": self.repo_id, "n": n}).all()
        except Exception as e:  # noqa: BLE001
            log.warning("pgvector search failed for %s (%s); FALLBACK to TF-IDF", self.repo_id, e)
            return None
        if not rows:
            return None  # repo was indexed without embeddings
        idx = self._ord_index
        return {idx.get(int(o), int(o)): max(0.0, float(s)) for o, s in rows}

    # ---------- cached agent outputs ----------

    def cache_get(self, name: str) -> Dict | None:
        with dbmod.SessionLocal() as db:
            a = db.get(RepoArtifact, (self.repo_id, name))
            return a.data if a else None

    def cache_put(self, name: str, value: Dict) -> None:
        with dbmod.SessionLocal() as db:
            a = db.get(RepoArtifact, (self.repo_id, name))
            if a:
                a.data = value
            else:
                db.add(RepoArtifact(repo_id=self.repo_id, name=name, data=value))
            db.commit()

    def cache_clear(self, *names: str) -> None:
        with dbmod.SessionLocal() as db:
            db.execute(delete(RepoArtifact).where(RepoArtifact.repo_id == self.repo_id,
                                                  RepoArtifact.name.in_(names)))
            db.commit()
