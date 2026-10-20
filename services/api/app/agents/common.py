"""Shared grounding helpers: system prompt, context formatting, CitationVerifier.

The verifier is the product's core promise: every `[path:L1-L2]` in model output
must exist in the snapshot. Valid citations are normalised to the real path so the
UI can open them; ghosts are removed from the text and reported.
"""
import logging
import os
import re
from typing import Iterable, List, Tuple

from ..chunk import Chunk
from ..store import RepoStore

log = logging.getLogger(__name__)

CITE_RE = re.compile(r"\[([^\[\]\s:]+?(?:\.[A-Za-z0-9]+|/[^\[\]\s:]+|[A-Za-z0-9_-]+)):L?(\d+)(?:\s*[-–]\s*L?(\d+))?\]")
MAX_CITED_SPAN = 400

# shipped inside the app package so the Docker image always has it (a missing prompt is a bug)
_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "prompts", "system.md")
with open(_PROMPT_PATH) as _f:
    SYSTEM_PROMPT = _f.read()


def ref(file: str, start: int, end: int) -> str:
    return f"[{file}:{start}-{end}]"


def format_context(hits: Iterable[Tuple[Chunk, float]], max_chars: int = 2200,
                   numbered: bool = False) -> str:
    parts = []
    for c, _ in hits:
        body = c.text[:max_chars]
        if numbered:
            body = "\n".join(f"{c.start_line + i:>4}| {ln}" for i, ln in enumerate(body.splitlines()))
        parts.append(f"--- {c.file}:{c.start_line}-{c.end_line} ---\n{body}")
    return "\n\n".join(parts)


def numbered(store: RepoStore, file: str, start: int, end: int) -> str:
    ls = store.lines(file)
    return "\n".join(f"{i:>4}| {ls[i - 1]}" for i in range(max(1, start), min(end, len(ls)) + 1))


def check_ref(store: RepoStore, file: str, start: int, end: int | None = None) -> dict | None:
    """Validate one reference; returns a normalised citation dict or None."""
    real = store.resolve(str(file or ""))
    if not real:
        return None
    try:
        s1 = int(start)
        s2 = int(end if end is not None else start)
    except (TypeError, ValueError):
        return None
    n = len(store.lines(real))
    if n == 0 or s1 < 1 or s2 < s1 or s1 > n or s2 - s1 > MAX_CITED_SPAN:
        return None
    s2 = min(s2, n)
    snippet = store.read(real, s1, min(s2, s1 + 14))
    if not snippet.strip():
        return None
    return {"file": real, "start_line": s1, "end_line": s2, "snippet": snippet[:1200]}


_MULTI = re.compile(r"\[([^\[\]\n]{3,300}?[,;][^\[\]\n]{1,300}?)\]")
_PART = re.compile(r"^\s*(?:([^\s:,;]+):)?L?(\d+)(?:\s*[-–]\s*L?(\d+))?\s*$")


def split_multi(markdown: str) -> str:
    """[a.py:1-5, 9-12; b.py:3] → [a.py:1-5] [a.py:9-12] [b.py:3-3] (models love these)."""
    def sub(m: re.Match) -> str:
        out, path = [], None
        for piece in re.split(r"[,;]", m.group(1)):
            p = _PART.match(piece)
            if not p or not (p.group(1) or path):
                return m.group(0)  # not a citation list — leave prose untouched
            path = p.group(1) or path
            out.append(f"[{path}:{p.group(2)}-{p.group(3) or p.group(2)}]")
        return " ".join(out)
    return _MULTI.sub(sub, markdown)


def verify_citations(store: RepoStore, markdown: str) -> Tuple[str, list, list]:
    """Parse [file:L1-L2]; keep only real ones. Returns (clean_md, citations, dropped)."""
    markdown = split_multi(markdown)
    cites: list = []
    dropped: list = []
    seen = set()

    def sub(m: re.Match) -> str:
        c = check_ref(store, m.group(1).strip(), m.group(2), m.group(3) or m.group(2))
        if not c:
            dropped.append(m.group(0))
            return ""
        k = (c["file"], c["start_line"], c["end_line"])
        if k not in seen:
            seen.add(k)
            cites.append(c)
        return ref(*k)

    clean = CITE_RE.sub(sub, markdown)
    clean = re.sub(r"[ \t]+([.,;:])", r"\1", clean)  # tidy space left by removed ghosts
    return clean, cites, dropped


def verify_text(store: RepoStore, text: str, sink: list, dropped: list) -> str:
    """verify_citations for a field inside a structured response; accumulates results."""
    clean, cites, drop = verify_citations(store, text or "")
    keys = {(c["file"], c["start_line"], c["end_line"]) for c in sink}
    sink.extend(c for c in cites if (c["file"], c["start_line"], c["end_line"]) not in keys)
    dropped.extend(drop)
    return clean.strip()


def _terms(query: str) -> set:
    from ..store import STOPWORDS
    return {t.rstrip("s") for t in re.findall(r"[a-z_]{3,}", query.lower())} - STOPWORDS


def _overlap(c: Chunk, terms: set) -> int:
    low = c.text.lower()
    return sum(t in low for t in terms)


def best_chunk(store: RepoStore, file: str, query: str) -> Chunk | None:
    cs = [c for c in store.chunks if c.file == file]
    if not cs:
        return None
    q = _terms(query)
    # prefer real definitions over the import header of the module
    return max(cs, key=lambda c: (_overlap(c, q) + (c.kind == "def"), -c.start_line))


def expand_by_imports(store: RepoStore, edges, hits: List[Tuple[Chunk, float]], query: str,
                      top: int = 6, per_file: int = 2, limit: int = 8) -> List[Tuple[Chunk, float]]:
    """Follow imports one hop from the best files, keeping only query-relevant targets."""
    q = _terms(query)
    have = {c.file for c, _ in hits}
    out: List[Tuple[Chunk, float]] = []
    for src in list(dict.fromkeys(c.file for c, _ in hits))[:top]:
        scored = []
        for e in edges:
            if e.src == src and e.dst not in have:
                c = best_chunk(store, e.dst, query)
                if c and _overlap(c, q):
                    scored.append((_overlap(c, q), c))
        for _, c in sorted(scored, key=lambda t: -t[0])[:per_file]:
            out.append((c, 0.0))
            have.add(c.file)
            if len(out) >= limit:
                return out
    return out


_DEF_RE = re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+(\w+)[ \t]*\(|"
                     r"^[ \t]*(?:export[ \t]+)?(?:async[ \t]+)?function[ \t]+(\w+)[ \t]*\(|"
                     r"^[ \t]*(?:export[ \t]+)?(?:const|let)[ \t]+(\w+)[ \t]*=[ \t]*(?:async[ \t]*)?\(", re.M)
_CALL_RE = re.compile(r"\b(?:([A-Za-z_]\w*)\.)?([A-Za-z_]\w*)[ \t]*\(")
_NOT_CALLS = {"if", "for", "while", "return", "print", "len", "str", "int", "dict", "list", "set",
              "tuple", "isinstance", "super", "range", "open", "max", "min", "sorted", "any", "all",
              "HTTPException", "Depends", "Field", "Query", "Body", "useState", "useEffect", "require"}


def _definitions(store: RepoStore) -> dict:
    """name → chunks that define it (Python def, JS/TS function or arrow const)."""
    cache = getattr(store, "_defs", None)
    if cache is not None and cache[0] == store.version:
        return cache[1]
    defs: dict = {}
    for c in store.chunks:
        for m in _DEF_RE.finditer(c.text):
            name = next(g for g in m.groups() if g)
            defs.setdefault(name, []).append(c)
    store._defs = (store.version, defs)
    return defs


def follow_calls(store: RepoStore, edges, chunks: List[Chunk], query: str,
                 top: int = 4, per_chunk: int = 2, limit: int = 4) -> List[Tuple[int, Chunk]]:
    """Definitions of functions the best chunks call (e.g. a route → `crud.create_user`).

    Only follows calls into files the caller imports (or a module named like the call's
    qualifier), so the tour keeps going along the real execution path. Returns
    (index of the calling chunk, callee chunk) pairs, most query-relevant first.
    """
    defs = _definitions(store)
    have = {(c.file, c.start_line) for c in chunks}
    q = _terms(query)
    out: List[Tuple[int, Chunk]] = []
    for i, caller in enumerate(chunks[:top]):
        imported = {e.dst for e in edges if e.src == caller.file}
        own = {next(g for g in m.groups() if g) for m in _DEF_RE.finditer(caller.text)}
        scored = {}
        for qual, name in _CALL_RE.findall(caller.text):
            if name in _NOT_CALLS or name in own or name not in defs:
                continue
            for c in defs[name]:
                stem = os.path.splitext(os.path.basename(c.file))[0]
                if c.file == caller.file or (c.file, c.start_line) in have:
                    continue
                if c.file in imported or (qual and qual == stem):
                    scored[(c.file, c.start_line)] = (len(q & _terms(name.replace("_", " "))), c)
        for _, c in sorted(scored.values(), key=lambda t: -t[0])[:per_chunk]:
            out.append((i, c))
            have.add((c.file, c.start_line))
            if len(out) >= limit:
                return out
    return out


def dedupe_hits(hits: List[Tuple[Chunk, float]]) -> List[Tuple[Chunk, float]]:
    seen, out = set(), []
    for c, s in hits:
        k = (c.file, c.start_line)
        if k not in seen:
            seen.add(k)
            out.append((c, s))
    return out
