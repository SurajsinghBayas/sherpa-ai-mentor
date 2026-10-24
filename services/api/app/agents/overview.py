"""Architecture overview — static analysis for structure, LLM for explanation.

Components and edges come from the real import graph (`analysis.py`); the model
only names/describes them, and every description must cite code that exists.
Results are cached per snapshot.
"""
from ..tracing import traced
import logging
import re
import threading

from ..analysis import Analysis, analyze, symbols_of
from ..llm import LLMError, llm
from ..store import RepoStore
from .common import SYSTEM_PROMPT, numbered, ref, check_ref, verify_text

log = logging.getLogger(__name__)

_analysis_cache: dict[tuple[str, str], Analysis] = {}
_lock = threading.Lock()
LAYERS = {"frontend", "backend", "api", "data", "infra", "tooling", "docs", "shared", "tests"}
MANIFESTS = ("README.md", "readme.md", "package.json", "pyproject.toml", "requirements.txt",
             "go.mod", "Cargo.toml", "Makefile", "docker-compose.yml", "compose.yml")


def get_analysis(store: RepoStore) -> Analysis:
    key = (store.repo_id, store.snapshot_hash)
    with _lock:
        if key not in _analysis_cache:
            _analysis_cache[key] = analyze(store)
        return _analysis_cache[key]


def _key_files(store: RepoStore, a: Analysis, files: list[str], n: int = 3) -> list[str]:
    indeg = a.in_degree()
    entry = {f for f, _, _ in a.entrypoints}
    return sorted(files, key=lambda f: (f not in entry, -indeg.get(f, 0),
                                        -len(symbols_of(store, f)), len(f)))[:n]


def _layer_guess(key: str) -> str:
    k = key.lower()
    for word, layer in (("test", "tests"), ("doc", "docs"), ("migrat", "data"), ("alembic", "data"),
                        ("model", "data"), ("schema", "data"), ("db", "data"), ("route", "api"),
                        ("api", "api"), ("controller", "api"), ("component", "frontend"),
                        ("page", "frontend"), ("ui", "frontend"), ("web", "frontend"),
                        ("frontend", "frontend"), ("client", "frontend"), ("hook", "frontend"),
                        ("server", "backend"), ("backend", "backend"), ("service", "backend"),
                        ("core", "backend"), ("script", "tooling"), ("infra", "infra"),
                        ("deploy", "infra"), ("docker", "infra")):
        if word in k:
            return layer
    return "shared"


def _mermaid(components: list[dict], edges: list[dict]) -> str:
    def nid(key: str) -> str:
        return "c_" + re.sub(r"[^A-Za-z0-9_]", "_", key)

    def label(s: str) -> str:
        return s.replace('"', "'").replace("[", "(").replace("]", ")")

    lines = ["flowchart LR"]
    by_layer: dict[str, list[dict]] = {}
    for c in components:
        by_layer.setdefault(c["layer"], []).append(c)
    for layer, comps in by_layer.items():
        lines.append(f'  subgraph L_{layer}["{layer}"]')
        for c in comps:
            lines.append(f'    {nid(c["key"])}["{label(c["name"])}<br/><small>{label(c["key"])}/</small>"]')
        lines.append("  end")
    for e in edges[:24]:
        lines.append(f'  {nid(e["from"])} -->|{e["count"]} import{"s" if e["count"] > 1 else ""}| {nid(e["to"])}')
    return "\n".join(lines)


def _context(store: RepoStore, a: Analysis) -> str:
    parts = []
    readme = next((f for f in store.files() if f.lower() in ("readme.md", "readme.rst", "readme")), None)
    if readme:
        parts.append(f"--- {readme}:1-60 ---\n{numbered(store, readme, 1, 60)}")
    for key, files in a.components.items():
        kf = _key_files(store, a, files)
        syms = []
        for f in kf:
            syms += [f"{n} ({k}) {f}:{s}-{e}" for n, s, e, k in symbols_of(store, f)[:6]]
        block = [f"=== COMPONENT {key}/ — {len(files)} files: "
                 + ", ".join(f.split("/")[-1] for f in files[:12])]
        if syms:
            block.append("symbols: " + "; ".join(syms[:10]))
        for f in kf[:2]:
            n = min(len(store.lines(f)), 35)
            block.append(f"--- {f}:1-{n} ---\n{numbered(store, f, 1, n)}")
        parts.append("\n".join(block))
    ctx = "\n\n".join(parts)
    return ctx[:60000]


def _fallback(store: RepoStore, a: Analysis) -> dict:
    comps = []
    for key, files in a.components.items():
        kf = _key_files(store, a, files)
        top = kf[0]
        n = min(len(store.lines(top)), 30)
        syms = [s[0] for f in kf for s in symbols_of(store, f)[:3]][:4]
        desc = (f"{len(files)} file(s); start with `{top}` {ref(top, 1, max(n, 1))}"
                + (f", which defines {', '.join(f'`{s}`' for s in syms)}." if syms else "."))
        comps.append({"key": key, "name": key.split("/")[-1].replace("-", " ").replace("_", " ").title()
                      if key != "(root)" else "Root", "layer": _layer_guess(key), "description": desc})
    entry = a.entrypoints[0] if a.entrypoints else None
    summary = (f"This repository has **{len(a.files)} files** in **{len(comps)} main components**, "
               f"connected by **{len(a.edges)} resolved imports**."
               + (f" Execution starts at `{entry[0]}` {ref(entry[0], entry[1], entry[1] + 10)}."
                  if entry else ""))
    return {"summary": summary, "components": comps, "flows": [], "start_here": [
        {"file": f, "start_line": ln, "end_line": ln + 15, "why": why} for f, ln, why in a.entrypoints[:3]]}


@traced("overview")
def build_overview(store: RepoStore, llm_override: dict | None = None, refresh: bool = False) -> dict:
    override = {k: v for k, v in (llm_override or {}).items() if v is not None}
    cached = store.cache_get("overview")
    if cached and not refresh and cached.get("snapshot") == store.snapshot_hash \
            and (cached.get("mode") == "llm" or not llm.can_use(override)):
        return cached
    a = get_analysis(store)
    keys = list(a.components)
    mode = "offline"
    raw = None
    if llm.can_use(override) and keys:
        prompt = (
            f"{_context(store, a)}\n\nCOMPONENT KEYS (use exactly): {keys}\n"
            "IMPORT EDGES between components (from static analysis): "
            + "; ".join(f"{x} -> {y} ({n})" for x, y, n, _ in a.component_edges()[:20])
            + "\nENTRYPOINTS: " + "; ".join(f"{f}:{ln} ({w})" for f, ln, w in a.entrypoints[:6])
            + "\n\nWrite an architecture overview for a newcomer as JSON:\n"
            '{"summary": "3-5 sentence markdown: what the system does and how the parts fit, with citations",\n'
            ' "components": [{"key": "<exact key>", "name": "2-4 word human name", '
            '"layer": "frontend|backend|api|data|infra|tooling|docs|shared|tests", '
            '"description": "1-2 sentences of markdown ending with >=1 citation"}],\n'
            ' "flows": [{"name": "e.g. User signup", "description": "1-2 sentences with citations"}],\n'
            ' "start_here": [{"file": "path", "start_line": 1, "end_line": 20, "why": "short reason"}]}\n'
            "Include EVERY component key once. 2-4 flows that a newcomer should trace. 3 start_here files.\n"
            "Citations look like [path/to/file.py:12-30] and must use paths + line numbers shown above.")
        try:
            raw = llm.complete_json(SYSTEM_PROMPT, prompt, max_tokens=3500, **override)
            mode = "llm"
        except (LLMError, ValueError) as e:
            log.warning("overview: FALLBACK to static overview (%s)", e)
    if raw is None:
        raw = _fallback(store, a)

    cites: list = []
    dropped: list = []
    by_key = {c.get("key"): c for c in raw.get("components", []) if isinstance(c, dict)}
    fb = {c["key"]: c for c in _fallback(store, a)["components"]}
    comps = []
    for key in keys:
        c = by_key.get(key) or fb[key]
        files = a.components[key]
        desc = verify_text(store, str(c.get("description", "")), cites, dropped)
        if "[" not in desc:  # model description lost its citations — use the grounded one
            desc = verify_text(store, fb[key]["description"], cites, dropped)
        layer = str(c.get("layer", "")).lower()
        comps.append({
            "key": key, "path": key, "name": str(c.get("name") or fb[key]["name"])[:40],
            "layer": layer if layer in LAYERS else _layer_guess(key),
            "role": layer if layer in LAYERS else _layer_guess(key),
            "description": desc, "files_count": len(files),
            "key_files": [{"file": f, "start_line": 1, "end_line": max(1, min(len(store.lines(f)), 40))}
                          for f in _key_files(store, a, files)]})
    name = {c["key"]: c["name"] for c in comps}
    edges = [{"from": x, "to": y, "count": n, "via": "imports",
              "from_name": name.get(x, x), "to_name": name.get(y, y),
              "example": {"file": e.src, "line": e.line}}
             for x, y, n, e in a.component_edges()]
    flows = []
    for f in raw.get("flows", [])[:4]:
        if isinstance(f, dict) and f.get("name"):
            flows.append({"name": str(f["name"])[:60],
                          "description": verify_text(store, str(f.get("description", "")), cites, dropped)})
    start = []
    for s in raw.get("start_here", [])[:4]:
        if isinstance(s, dict):
            c = check_ref(store, s.get("file"), s.get("start_line", 1), s.get("end_line", s.get("start_line", 1)))
            if c:
                start.append({**c, "why": str(s.get("why", ""))[:200]})
    out = {
        "summary": verify_text(store, str(raw.get("summary", "")), cites, dropped)
        or _fallback(store, a)["summary"],
        "components": comps, "edges": edges, "mermaid": _mermaid(comps, edges),
        "flows": flows, "start_here": start,
        "entrypoints": [{"file": f, "line": ln, "why": w} for f, ln, w in a.entrypoints[:6]],
        "stats": {"files": len(store.files()), "chunks": len(store.chunks),
                  "imports": len(a.edges), "languages": store.meta.get("languages", [])},
        "citations": cites, "dropped": dropped, "mode": mode,
        "model": (override.get("model") or llm.model) if mode == "llm" else None,
        "snapshot": store.snapshot_hash,
    }
    if dropped:
        log.info("overview: removed %d unverifiable citation(s)", len(dropped))
    store.cache_put("overview", out)
    return out
