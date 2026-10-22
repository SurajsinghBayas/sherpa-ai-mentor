"""Spoken questions → the repo's own names.

Speech recognition hears code as words: "get current user", "deps dot py", "fast API",
"tan stack query". Before a spoken question is shown or answered, runs of words that
spell an identifier, file or library that actually exists in the indexed repo are
replaced with it, so "what does get current user in deps dot py do" becomes
"what does get_current_user in deps.py do". Only names found in the repo are used, so
ordinary English is left alone.
"""
import re
from difflib import get_close_matches
from functools import lru_cache
from typing import Dict, List

from .store import RepoStore

MAX_WORDS = 4          # longest run of spoken words that can spell one name
MIN_KEY = 6            # shorter collapsed names are too easily ordinary words
FUZZY = 0.9            # similarity for near-misses ("fastapy" → fastapi)

DEFINITION = re.compile(
    r"\b(?:def|class|function|interface|type|enum|struct|const|let|var|fn|func)\s+([A-Za-z_][A-Za-z0-9_]{3,})")
IMPORT = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w]*)|from\s+['\"](@?[\w-]+)(?:/[\w-]+)?['\"]", re.M)
# how libraries are written, when the import name is all lowercase
DISPLAY = {"fastapi": "FastAPI", "sqlmodel": "SQLModel", "sqlalchemy": "SQLAlchemy", "pydantic": "Pydantic",
           "tanstack": "TanStack", "pgvector": "pgvector", "nextjs": "Next.js", "openai": "OpenAI",
           "graphql": "GraphQL", "postgres": "Postgres", "postgresql": "PostgreSQL", "jwt": "JWT"}
SPOKEN_DOT = {"dot", "point", "period"}
WORD = re.compile(r"[A-Za-z0-9_']+|[^\sA-Za-z0-9_']+")


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


@lru_cache(maxsize=32)
def _vocabulary(repo_id: str, version: int, names: tuple) -> Dict[str, str]:
    vocab: Dict[str, str] = {}
    for name in names:
        k = _key(name)
        if len(k) >= MIN_KEY:
            vocab.setdefault(k, name)
    return vocab


def vocabulary(store: RepoStore) -> Dict[str, str]:
    """collapsed spelling ("getcurrentuser", "depspy") → the name as written in the repo."""
    names: set = set()
    for path in store.files():
        base = path.rsplit("/", 1)[-1]
        names.add(base)                       # deps.py
        stem = base.rsplit(".", 1)[0]
        if "_" in stem or any(ch.isupper() for ch in stem[1:]):
            names.add(stem)                   # use_auth, UserCard
    for c in store.chunks:
        names.update(DEFINITION.findall(c.text))
        for a, b in IMPORT.findall(c.text):
            lib = (a or b).lstrip("@")
            names.add(DISPLAY.get(lib.lower(), lib))
    names.update(DISPLAY.values())
    # names with a separator or inner capital are clearly code; plain words stay out
    names = {n for n in names if re.search(r"[._]|[a-z][A-Z]", n) or n in DISPLAY.values()
             or n.lower() in DISPLAY}
    return _vocabulary(store.repo_id, store.version, tuple(sorted(names)))


_initials: Dict[int, Dict[str, tuple]] = {}


def _by_initial(vocab: Dict[str, str]) -> Dict[str, tuple]:
    """Names grouped by first letter, so near-miss matching only compares likely candidates."""
    got = _initials.get(id(vocab))
    if got is None:
        groups: Dict[str, list] = {}
        for k in vocab:
            groups.setdefault(k[0], []).append(k)
        got = {c: tuple(ks) for c, ks in groups.items()}
        if len(_initials) > 64:
            _initials.clear()
        _initials[id(vocab)] = got
    return got


def correct(text: str, vocab: Dict[str, str]) -> str:
    """Replace spoken spellings of known names; everything else is returned unchanged."""
    if not text or not vocab:
        return text
    tokens = WORD.findall(text)
    words = [i for i, t in enumerate(tokens) if re.match(r"[A-Za-z0-9_']", t)]
    out: List[str] = []
    i = 0  # index into `words`
    pos = 0  # index into `tokens` already emitted
    while i < len(words):
        hit = None
        # exact spellings first, at every length; near-misses only when nothing matches exactly,
        # so "get current user in" can't swallow the "in" by being close to get_current_user
        for fuzzy in (False, True):
            for n in range(min(MAX_WORDS, len(words) - i), 0, -1):
                span = [tokens[words[j]] for j in range(i, i + n)]
                if span[0].lower() in SPOKEN_DOT or span[-1].lower() in SPOKEN_DOT:
                    continue
                k = _key("".join("." if w.lower() in SPOKEN_DOT else w for w in span))
                name = vocab.get(k)
                if name is None and fuzzy and len(k) >= 8:
                    near = [c for c in get_close_matches(k, _by_initial(vocab).get(k[0], ()), n=3, cutoff=FUZZY)
                            if abs(len(c) - len(k)) <= 1]
                    name = vocab[near[0]] if near else None
                if name and (n > 1 or span[0] != name):
                    hit = (n, name)
                    break
            if hit:
                break
        if hit:
            n, name = hit
            first, last = words[i], words[i + n - 1]
            out.extend(tokens[pos:first])
            out.append(name)
            pos = last + 1
            i += n
        else:
            i += 1
    out.extend(tokens[pos:])
    # re-join: tokens were split on whitespace, so put single spaces back between words
    return re.sub(r"\s+([?.!,;:])", r"\1", " ".join(t for t in out if t.strip())).strip()
