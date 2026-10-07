"""Hybrid store: SQLite FTS5 (keywords) + TF-IDF vectors (semantic-lite).

Production path swaps `TfidfVectorizer` for pgvector/OpenAI embeddings
without changing the `Store` interface — see `search()` contract.
Persists per-repo under DATA_DIR/<repo_id>/ (chunks.json + meta.json).
"""
import json
import os
import re
from dataclasses import asdict
from typing import Dict, List, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .chunk import Chunk


TOKEN = re.compile(r"[a-zA-Z_][a-zA-Z0-9_./-]*")


class RepoStore:
    def __init__(self, data_dir: str, repo_id: str):
        self.dir = os.path.join(data_dir, repo_id)
        os.makedirs(self.dir, exist_ok=True)
        self.chunks_path = os.path.join(self.dir, "chunks.json")
        self.meta_path = os.path.join(self.dir, "meta.json")
        self.chunks: List[Chunk] = []
        self.vectorizer: TfidfVectorizer | None = None
        self.matrix = None
        self.meta: Dict = {}
        self._load()

    def _load(self):
        if os.path.exists(self.chunks_path):
            with open(self.chunks_path) as f:
                raw = json.load(f)
            self.chunks = [Chunk(**c) for c in raw]
            if os.path.exists(self.meta_path):
                with open(self.meta_path) as f:
                    self.meta = json.load(f)
            self._reindex()

    def save(self, chunks: List[Chunk], meta: Dict):
        self.chunks = chunks
        self.meta = meta
        with open(self.chunks_path, "w") as f:
            json.dump([asdict(c) for c in chunks], f)
        with open(self.meta_path, "w") as f:
            json.dump(meta, f)
        self._reindex()

    def _reindex(self):
        if not self.chunks:
            return
        corpus = [f"{c.file}\n{c.text}" for c in self.chunks]
        self.vectorizer = TfidfVectorizer(max_features=8000, ngram_range=(1, 2))
        try:
            self.matrix = self.vectorizer.fit_transform(corpus)
        except ValueError:
            self.vectorizer = None
            self.matrix = None

    def _keyword_scores(self, query: str) -> List[float]:
        qtokens = set(t.lower() for t in TOKEN.findall(query))
        scores = []
        for c in self.chunks:
            hay = f"{c.file} {c.text}".lower()
            hits = sum(1 for t in qtokens if t and t in hay)
            # boost filenames / route-ish / handler-ish chunks
            boost = 1.5 if any(k in c.file.lower() for k in ("route", "handler", "auth", "user", "api", "view", "controller")) else 1.0
            scores.append(hits * boost)
        return scores

    def search(self, query: str, k: int = 8) -> List[Tuple[Chunk, float]]:
        if not self.chunks:
            return []
        kw = self._keyword_scores(query)
        vec = [0.0] * len(self.chunks)
        if self.vectorizer is not None and self.matrix is not None:
            try:
                qv = self.vectorizer.transform([query])
                sims = cosine_similarity(qv, self.matrix)[0]
                vec = list(sims)
            except Exception:
                pass
        # hybrid: normalize + combine
        def norm(xs):
            m = max(xs) if max(xs) > 0 else 1.0
            return [x / m for x in xs]
        kw_n, vec_n = norm(kw), norm(vec)
        scored = [(c, 0.55 * v + 0.45 * w) for c, v, w in zip(self.chunks, vec_n, kw_n)]
        # MMR-lite: penalize near-duplicate files to diversify
        seen: Dict[str, int] = {}
        diverse = []
        for c, s in sorted(scored, key=lambda x: -x[1]):
            penalty = 0.12 * seen.get(c.file, 0)
            diverse.append((c, s - penalty))
            seen[c.file] = seen.get(c.file, 0) + 1
        return sorted(diverse, key=lambda x: -x[1])[:k]

    def read(self, path: str, start: int, end: int) -> str:
        rel = path.lstrip("./")
        for c in self.chunks:
            if c.file == path or c.file.endswith(rel) or rel.endswith(c.file):
                if c.start_line <= start and end <= c.end_line + 200:
                    pass
        # authoritative read: reconstruct from overlapping chunks of same file
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
