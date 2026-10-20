"""Thin retrieval facade — keeps agent code clean and pgvector-swappable."""
import re
from typing import List, Tuple
from .chunk import Chunk
from .config import settings
from .store import RepoStore


def retrieve(store: RepoStore, query: str, k: int | None = None) -> List[Tuple[Chunk, float]]:
    return store.search(query, k or settings.max_chunks_per_query)


ALIASES = [
    (r"\bsign(?:s|ed|ing)?[\s-]?up\b|\bregist(?:er|ers|ered|ering|ration)\b|\bonboard",
     "signup register create user auth route handler"),
    (r"\blog(?:s|ged|ging)?[\s-]?in\b|\bsign(?:s|ed|ing)?[\s-]?in\b|\bauthenticat",
     "login authenticate session token password"),
    (r"\blog(?:s|ged|ging)?[\s-]?out\b", "logout session token"),
    (r"\bauth|\bpermission|\bjwt|\btoken", "auth login jwt session middleware dependency"),
    (r"\bdatabase|\bdb\b|\bpersist|\bstor(?:e|ed|age)\b", "model schema migration db session"),
    (r"\bfrontend|\bfront-end|\bui\b|\bbrowser|\bclient\b",
     "frontend client sdk service fetch request hook query mutation"),
    (r"\bapi\b|\bendpoint", "route router handler endpoint"),
    (r"\bentry ?point|\bstart(?:s|ed)? up|\bboot", "main app server index"),
    (r"\bconfig|\bsettings|\benv(?:ironment)? var", "settings config env"),
    (r"\bpassword|\breset", "password hash reset email token"),
    (r"\btest(?:s|ing)?\b", "test pytest spec fixture"),
]


def expand_aliases(question: str) -> str:
    """Map newcomer phrasing → code vocabulary (helps lexical retrieval a lot)."""
    low = question.lower()
    extra = [v for pat, v in ALIASES if re.search(pat, low)]
    return f"{question} {' '.join(extra)}" if extra else question
