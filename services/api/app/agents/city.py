"""Repo City: the codebase as a city, and how it grew.

Each component (the same grouping as the architecture map) is a district; each source file is
a building whose height is its line count and whose footprint is its number of definitions.
Commit history (app/history.py) adds when each file appeared, how often it changed and when it
last did, plus the commit-by-commit timeline the web app plays back. No language model is used,
so the city is free and quick to build.
"""
import logging
import time

from ..history import fetch_history
from ..store import RepoStore
from .overview import get_analysis
from ..analysis import symbols_of

log = logging.getLogger(__name__)

MAX_BUILDINGS = 600     # biggest files first; the rest are counted, not drawn
MAX_TIMELINE = 400      # commits played back; older ones are merged into the first frame
MAX_OTHER = 80          # docs and config files, drawn as low buildings in their own district
OTHER = "(docs & config)"


def _history(store: RepoStore, refresh: bool) -> dict | None:
    """Commit history, cached per indexed commit (fetched again only when the repo moves on)."""
    cached = store.cache_get("history")
    commit = store.meta.get("commit") or store.snapshot_hash
    if cached and cached.get("commit") == commit and not refresh:
        return cached.get("history")
    h = fetch_history(store.meta)
    store.cache_put("history", {"commit": commit, "history": h, "fetched_at": time.time()})
    return h


def _district_names(store: RepoStore) -> dict[str, str]:
    ov = store.cache_get("overview") or {}
    return {c["key"]: c["name"] for c in ov.get("components", []) if isinstance(c, dict) and "key" in c}


def build_city(store: RepoStore, refresh: bool = False) -> dict:
    cached = store.cache_get("city")
    if cached and not refresh and cached.get("snapshot") == store.snapshot_hash:
        return cached
    a = get_analysis(store)
    code = {f for files in a.components.values() for f in files}  # components group source files only
    sizes = {f: len(store.lines(f)) for f in code}
    kept = set(sorted(code, key=lambda f: -sizes[f])[:MAX_BUILDINGS])
    names = _district_names(store)
    other = sorted((f for f in store.files() if f not in code), key=lambda f: -len(store.lines(f)))[:MAX_OTHER]
    for f in other:
        sizes[f] = len(store.lines(f))
    kept.update(other)
    groups = {**a.components, **({OTHER: other} if other else {})}
    names[OTHER] = "Docs & config"

    districts, buildings, index = [], [], {}
    for key, files in groups.items():
        members = sorted((f for f in files if f in kept), key=lambda f: (-sizes[f], f))
        if not members:
            continue
        d = len(districts)
        districts.append({"key": key, "code": key != OTHER, "name": names.get(key) or (key.split("/")[-1].replace("_", " ")
                                                                    .replace("-", " ").title() if key != "(root)" else "Root"),
                          "files": len(files)})
        for f in members:
            index[f] = len(buildings)
            buildings.append({"path": f, "district": d, "lines": sizes[f],
                              "defs": len(symbols_of(store, f)) if f in code else 0,
                              "changes": 0, "born": 0, "last": None})

    edges = [list(x) for x in sorted({(index[e.src], index[e.dst]) for e in a.edges
                                      if e.src in index and e.dst in index and e.src != e.dst})]

    history = _history(store, refresh)
    timeline: list[dict] = []
    if history and history.get("commits"):
        commits = history["commits"]
        frames = []
        for c in commits:
            touched = sorted({index[p] for _, p in c["files"] if p in index})
            added = sorted({index[p] for s, p in c["files"] if s == "A" and p in index})
            if touched:
                frames.append({"t": c["t"], "sha": c["sha"], "subject": c["subject"],
                               "changed": touched, "added": added})
        if history.get("truncated") and frames and frames[0]["sha"] == commits[0]["sha"]:
            # a cut-off history's oldest commit lists the whole tree as new: it is the starting point
            frames[0].update(subject="Where the history starts", start=True, added=frames[0]["changed"])
        if len(frames) > MAX_TIMELINE:  # older commits become one opening frame
            head, frames = frames[:-MAX_TIMELINE + 1], frames[-MAX_TIMELINE + 1:]
            merged = sorted({i for f in head for i in f["changed"]})
            frames.insert(0, {"t": head[-1]["t"], "sha": head[-1]["sha"],
                              "subject": f"{len(head)} earlier commits", "changed": merged,
                              "added": sorted({i for f in head for i in f["added"]})})
        born: dict[int, int] = {}
        for n, fr in enumerate(frames):
            for i in fr["changed"]:
                buildings[i]["changes"] += 1
                buildings[i]["last"] = fr["t"]
            for i in fr["added"]:
                born.setdefault(i, n)
        # a file the window never adds (first seen modified, or never touched) was already
        # standing when the window starts
        for i, b in enumerate(buildings):
            b["born"] = born.get(i, 0)
        timeline = frames

    out = {
        "districts": districts, "buildings": buildings, "edges": edges, "timeline": timeline,
        "history": "full" if history and not history.get("truncated") else
                   "recent" if history else "none",
        "stats": {"files": len(store.files()), "drawn": len(buildings), "commits": len(timeline),
                  "lines": sum(sizes.values())},
        "snapshot": store.snapshot_hash,
    }
    store.cache_put("city", out)
    return out
