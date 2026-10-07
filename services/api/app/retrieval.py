"""Thin retrieval facade — keeps agent code clean and pgvector-swappable."""
from typing import List, Tuple
from .chunk import Chunk
from .config import settings
from .store import RepoStore


def retrieve(store: RepoStore, query: str, k: int | None = None) -> List[Tuple[Chunk, float]]:
    return store.search(query, k or settings.max_chunks_per_query)


def expand_aliases(question: str) -> str:
    q = question
    low = question.lower()
    # map newcomer phrasing → code vocabulary (helps offline TF-IDF a lot)
    aliases = {
        "sign up": "signup register create user auth route handler",
        "signup": "signup register create user auth route handler",
        "log in": "login authenticate session token",
        "auth": "auth login jwt session middleware",
        "database": "model schema migration db session",
        "api": "route router handler endpoint",
        "entrypoint": "main app server index",
        "config": "settings config env",
    }
    extra = [v for k, v in aliases.items() if k in low]
    return f"{q} {' '.join(extra)}" if extra else q
