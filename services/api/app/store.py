"""Hybrid store: keyword scores + semantic vectors.

Vectors come from the backend (Bedrock embeddings in Postgres/pgvector) when it has
them, else from an in-memory TF-IDF index — so search works offline and in tests.
Persistence is pluggable: `MemoryBackend` (tests, scratch) or `SqlBackend`
(app/persist.py — Postgres in the cloud, SQLite locally).
"""
import hashlib
import json
import logging
import os
import re
from typing import Dict, List, Optional, Protocol, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .chunk import Chunk


log = logging.getLogger(__name__)

TOKEN = re.compile(r"[a-zA-Z_][a-zA-Z0-9_./-]*")
STOPWORDS = {"the", "and", "for", "what", "when", "where", "which", "how", "why", "does", "this",
             "that", "with", "from", "into", "happen", "happens", "work", "works", "code", "file",
             "files", "are", "can", "you", "about", "explain", "show", "there", "they", "their",
             "its", "has", "have", "use", "used", "using", "get", "gets", "set", "after", "before"}
ROUTE_HINTS = ("route", "handler", "auth", "user", "api", "view", "controller")
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|e2e)/|test_|_test\.|\.test\.|\.spec\.")
# dev-only / private / debug code: real but rarely what a newcomer means (e.g. a /private/users
# route that seeds accounts in local dev must not outrank the public /signup endpoint)
DEV_PATH = re.compile(r"(^|/)(private|dev|debug|internal|mocks?|fixtures|sandbox|playground)(/|\.|_|$)")
ROUTE_DECORATOR = re.compile(r"@\w*(?:router|app|bp|blueprint)\.(?:get|post|put|patch|delete|route)\(|"
                             r"\b(?:router|app)\.(?:get|post|put|patch|delete)\(\s*['\"]", re.I)


def _stem(t: str) -> str:
    return t[:-1] if len(t) > 4 and t.endswith("s") and not t.endswith("ss") else t


class Backend(Protocol):
    def load(self) -> Optional[Tuple[List[Chunk], Dict, Dict[str, str], int]]: ...
    def save(self, chunks: List[Chunk], meta: Dict, sources: Dict[str, str]) -> int: ...
    def cache_get(self, name: str) -> Dict | None: ...
    def cache_put(self, name: str, value: Dict) -> None: ...
    def cache_clear(self, *names: str) -> None: ...
    def vector_scores(self, query: str, n: int) -> Optional[Dict[int, float]]: ...


class MemoryBackend:
    """Keeps everything in the process — for tests and throwaway stores."""

    def __init__(self):
        self.artifacts: Dict[str, Dict] = {}
        self.version = 0

    def load(self):
        return None

    def save(self, chunks, meta, sources) -> int:
        self.version += 1
        return self.version

    def cache_get(self, name):
        return self.artifacts.get(name)

    def cache_put(self, name, value):
        self.artifacts[name] = value

    def cache_clear(self, *names):
        for n in names:
            self.artifacts.pop(n, None)

    def vector_scores(self, query, n):
        return None


class RepoStore:
    def __init__(self, repo_id: str, backend: Backend | None = None):
        self.repo_id = repo_id
        self.backend: Backend = backend or MemoryBackend()
        self.chunks: List[Chunk] = []
        self.sources: Dict[str, str] = {}
        self.meta: Dict = {}
        self.version = 0
        self._tfidf: Tuple[TfidfVectorizer, object] | None = None
        loaded = self.backend.load()
        if loaded:
            self.chunks, self.meta, self.sources, self.version = loaded

    def save(self, chunks: List[Chunk], meta: Dict, sources: Dict[str, str] | None = None):
        self.chunks = chunks
        self.meta = meta
        self.sources = sources or {}
        if self.sources:
            meta.setdefault("file_hashes", {p: file_hash(t) for p, t in self.sources.items()})
        self._tfidf = None
        self.version = self.backend.save(chunks, meta, self.sources)

    # ---------- cached agent outputs (overview, docs, tasks …) ----------

    def cache_get(self, name: str) -> Dict | None:
        return self.backend.cache_get(name)

    def cache_put(self, name: str, value: Dict) -> None:
        self.backend.cache_put(name, value)

    def cache_clear(self, *names: str) -> None:
        self.backend.cache_clear(*names)

    @property
    def snapshot_hash(self) -> str:
        hashes = self.meta.get("file_hashes") or {c.file: str(c.end_line) for c in self.chunks}
        return hashlib.sha1(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:12]

    def _tfidf_scores(self, query: str) -> List[float]:
        if self._tfidf is None:
            vec = TfidfVectorizer(max_features=8000, ngram_range=(1, 2))
            try:
                self._tfidf = (vec, vec.fit_transform([f"{c.file}\n{c.text}" for c in self.chunks]))
            except ValueError as e:
                log.warning("TF-IDF index failed for %s (%s); search falls back to "
                            "keyword-only", self.repo_id, e)
                self._tfidf = (None, None)
        vec, matrix = self._tfidf
        if vec is None:
            return [0.0] * len(self.chunks)
        try:
            return list(cosine_similarity(vec.transform([query]), matrix)[0])
        except Exception as e:  # noqa: BLE001
            log.warning("TF-IDF query failed (%s); using keyword-only scores", e)
            return [0.0] * len(self.chunks)

    def _vector_scores(self, query: str) -> List[float]:
        """Embedding similarity from the backend; TF-IDF when it has none."""
        sims = self.backend.vector_scores(query, max(60, len(self.chunks) // 8))
        if not sims:
            return self._tfidf_scores(query)
        return [sims.get(i, 0.0) for i in range(len(self.chunks))]

    @staticmethod
    def _wants_dev(tokens) -> bool:
        return bool(set(tokens) & {"private", "dev", "debug", "internal", "mock", "mocks",
                                   "fixture", "fixtures", "sandbox", "seed", "local"})

    def _keyword_scores(self, query: str) -> List[float]:
        qtokens = {_stem(t.lower()) for t in TOKEN.findall(query)}
        qtokens = {t for t in qtokens if len(t) >= 3 and t not in STOPWORDS}
        wants_tests = any(t.startswith("test") for t in qtokens)
        wants_dev = self._wants_dev(qtokens)
        scores = []
        for c in self.chunks:
            hay = f"{c.file} {c.text}".lower()
            hits = sum(1 for t in qtokens if t in hay)
            path = c.file.lower()
            # boost route/handler-ish files; demote tests and docs unless asked for
            boost = 1.5 if any(k in path for k in ROUTE_HINTS) else 1.0
            if not wants_tests and TEST_PATH.search(path):
                boost *= 0.55
            if not wants_dev and DEV_PATH.search(path):
                boost *= 0.5
            if path.startswith("web/") or path.endswith((".md", ".mdx", ".json", ".lock")):
                boost *= 0.8
            if re.search(r"changelog|release[-_ ]?notes|history\.md|license", path):
                boost *= 0.4
            # a file named after the topic ("configuration" → config.py) is a strong signal
            stem = os.path.splitext(path.rsplit("/", 1)[-1])[0]
            if len(stem) >= 4 and any(t == stem or (len(t) >= 5 and t.startswith(stem)) for t in qtokens):
                boost *= 1.7
            # an endpoint whose route string matches the query is almost always the answer
            if any(f'/{t}' in hay for t in qtokens) and ROUTE_DECORATOR.search(c.text):
                boost *= 1.6
            scores.append(hits * boost)
        return scores

    def search(self, query: str, k: int = 8) -> List[Tuple[Chunk, float]]:
        if not self.chunks:
            return []
        kw = self._keyword_scores(query)
        vec = self._vector_scores(query)
        # hybrid: normalize + combine
        def norm(xs):
            m = max(xs) if max(xs) > 0 else 1.0
            return [x / m for x in xs]
        kw_n, vec_n = norm(kw), norm(vec)
        wants_tests = "test" in query.lower()
        wants_dev = self._wants_dev({t.lower() for t in TOKEN.findall(query)})

        def demote(path: str) -> float:
            f = 0.7 if not wants_tests and TEST_PATH.search(path) else 1.0
            return f * (0.7 if not wants_dev and DEV_PATH.search(path) else 1.0)

        scored = [(c, (0.55 * v + 0.45 * w) * demote(c.file.lower()))
                  for c, v, w in zip(self.chunks, vec_n, kw_n)]
        # MMR-lite: penalize near-duplicate files to diversify
        seen: Dict[str, int] = {}
        diverse = []
        for c, s in sorted(scored, key=lambda x: -x[1]):
            penalty = 0.12 * seen.get(c.file, 0)
            diverse.append((c, s - penalty))
            seen[c.file] = seen.get(c.file, 0) + 1
        return sorted(diverse, key=lambda x: -x[1])[:k]

    def resolve(self, path: str) -> str | None:
        """Exact path, else unique-ish suffix match (models often emit short paths)."""
        files = self.files()
        if path in files:
            return path
        rel = path.strip().lstrip("./")
        cands = [f for f in files if f.endswith("/" + rel) or f == rel]
        return min(cands, key=len) if cands else None

    def lines(self, path: str) -> List[str]:
        """All lines of a file (full text when available, else rebuilt from chunks)."""
        real = self.resolve(path)
        if not real:
            return []
        if real in self.sources:
            return self.sources[real].splitlines()
        out: Dict[int, str] = {}
        for c in self.chunks:
            if c.file == real:
                for i, ln in enumerate(c.text.splitlines()):
                    out[c.start_line + i] = ln
        return [out.get(i, "") for i in range(1, max(out) + 1)] if out else []

    def read(self, path: str, start: int, end: int) -> str:
        rel = path.lstrip("./")
        if self.resolve(path) in self.sources:
            ls = self.lines(path)
            return "\n".join(ls[max(start, 1) - 1:end])
        # legacy snapshots: reconstruct from overlapping chunks of same file
        file_chunks = sorted([c for c in self.chunks if c.file == path],
                             key=lambda c: c.start_line)
        if not file_chunks:
            # try suffix match
            cands = [c for c in self.chunks if c.file.endswith(rel)]
            files = sorted(set(c.file for c in cands))
            if files:
                file_chunks = sorted([c for c in self.chunks if c.file == files[0]],
                                     key=lambda c: c.start_line)
        lines: Dict[int, str] = {}
        for c in file_chunks:
            for i, ln in enumerate(c.text.splitlines()):
                lines[c.start_line + i] = ln
        if not lines:
            return ""
        return "\n".join(lines.get(i, "") for i in range(start, end + 1))

    def files(self) -> List[str]:
        return sorted(set(c.file for c in self.chunks))


def file_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[:16]
