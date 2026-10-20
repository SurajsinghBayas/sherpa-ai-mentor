"""Living onboarding docs — generated from the code and kept in sync with it.

Each section records the hash of every file it cites. After a re-sync, sections
whose sources changed (or vanished) are marked stale and regenerated from the new
code; untouched sections are left alone. A changelog records every refresh.
"""
import logging
import re
import time

from ..llm import LLMError, llm
from ..retrieval import retrieve
from ..store import RepoStore
from .common import SYSTEM_PROMPT, format_context, numbered, ref, verify_text

log = logging.getLogger(__name__)

SECTIONS = [
    ("what", "What this project is", "purpose, users, and the main features"),
    ("architecture", "Architecture", "the main components, how they connect, and the request path"),
    ("setup", "Run it locally", "prerequisites, install, configuration/env vars, and the commands to start and test it"),
    ("flows", "Key flows", "2-3 important flows (e.g. signup, a core API call) traced through the files"),
    ("conventions", "Conventions & where to start", "code layout conventions, testing, and the first files a newcomer should read"),
]
SETUP_FILES = ("README.md", "readme.md", "Makefile", "package.json", "pyproject.toml",
               "requirements.txt", "docker-compose.yml", "compose.yml", ".env.example",
               "CONTRIBUTING.md", "development.md", "Dockerfile")


def _hashes(store: RepoStore) -> dict:
    return store.meta.get("file_hashes", {})


def _context_for(store: RepoStore, section_id: str, overview: dict) -> str:
    parts = []
    if section_id in ("what", "architecture", "conventions", "flows"):
        parts.append("Architecture overview (already verified):\n" + overview.get("summary", "")
                     + "\n" + "\n".join(f"- {c['name']} ({c['key']}/): {c['description']}"
                                         for c in overview.get("components", [])))
    if section_id in ("setup", "what", "conventions"):
        for f in store.files():
            if f.split("/")[-1] in SETUP_FILES and f.count("/") <= 1:
                n = min(len(store.lines(f)), 70)
                parts.append(f"--- {f}:1-{n} ---\n{numbered(store, f, 1, n)}")
    if section_id == "flows":
        for fl in overview.get("flows", [])[:3]:
            hits = retrieve(store, fl["name"] + " route handler", 4)
            parts.append(f"Flow: {fl['name']} — {fl['description']}\n" + format_context(hits, 1500, numbered=True))
    if section_id in ("architecture", "conventions"):
        for e in overview.get("entrypoints", [])[:3]:
            parts.append(f"--- {e['file']}:{e['line']}-{e['line'] + 25} ---\n"
                         + numbered(store, e["file"], e["line"], e["line"] + 25))
    return "\n\n".join(parts)[:40000]


def _write_section(store: RepoStore, sid: str, title: str, brief: str, overview: dict,
                   override: dict, changed: list[str] | None = None) -> dict:
    ctx = _context_for(store, sid, overview)
    extra = ""
    if changed:
        extra = ("\n\nThese files CHANGED since the last version of this section — re-read them and "
                 "update anything that is now wrong:\n" + "\n\n".join(
                     f"--- {f}:1-{min(len(store.lines(f)), 80)} ---\n{numbered(store, f, 1, 80)}"
                     for f in changed[:4] if store.resolve(f)))
    md, mode = "", "offline"
    if llm.can_use(override):
        try:
            md = llm.complete(SYSTEM_PROMPT, (
                f"{ctx}{extra}\n\nWrite the '{title}' section of an onboarding guide for new "
                f"developers: {brief}. GitHub markdown, 80-220 words, use ### subheadings or bullets "
                "where helpful, `inline code` for commands/paths, and ```bash blocks for commands. "
                "Do NOT repeat the section title as a heading. Every factual bullet/sentence ends with a "
                "citation [path:start-end] copied from the context headers or a narrower range inside."),
                max_tokens=1400, **override)
            mode = "llm"
        except LLMError as e:
            log.warning("docs: FALLBACK to extractive section %r (%s)", sid, e)
    if not md:
        md = _fallback_section(store, sid, overview)
    cites: list = []
    dropped: list = []
    md = verify_text(store, re.sub(rf"^#+\s*{re.escape(title)}\s*\n", "", md.strip(), flags=re.I),
                     cites, dropped)
    h = _hashes(store)
    return {"id": sid, "title": title, "markdown": md, "mode": mode,
            "sources": {c["file"]: h.get(c["file"], "") for c in cites},
            "citations": cites, "dropped": dropped, "updated_at": time.time()}


def _fallback_section(store: RepoStore, sid: str, overview: dict) -> str:
    if sid in ("what", "architecture"):
        return overview.get("summary", "") + "\n\n" + "\n".join(
            f"- **{c['name']}** — {c['description']}" for c in overview.get("components", []))
    if sid == "setup":
        for f in store.files():
            if f.lower() == "readme.md":
                ls = store.lines(f)
                for i, ln in enumerate(ls, 1):
                    if re.search(r"install|setup|getting started|quick ?start|development", ln, re.I) and ln.startswith("#"):
                        return f"See the README's setup instructions {ref(f, i, min(i + 30, len(ls)))}."
        return "No setup instructions were found in the repository."
    if sid == "flows":
        return "\n".join(f"- **{fl['name']}** — {fl['description']}" for fl in overview.get("flows", [])) \
            or "Use the Code Tour tab to trace a flow."
    return "\n".join(f"- `{s['file']}` {ref(s['file'], s['start_line'], s['end_line'])} — {s.get('why', '')}"
                     for s in overview.get("start_here", [])) or "Start from the entrypoints in the architecture map."


def generate_docs(store: RepoStore, llm_override: dict | None = None) -> dict:
    from .overview import build_overview
    override = {k: v for k, v in (llm_override or {}).items() if v is not None}
    ov = build_overview(store, override)
    sections = [_write_section(store, sid, t, b, ov, override) for sid, t, b in SECTIONS]
    doc = {"repo": store.meta.get("name", store.repo_id), "generated_at": time.time(),
           "snapshot": store.snapshot_hash, "sections": sections,
           "changelog": [{"at": time.time(), "event": "generated",
                          "sections": [s["id"] for s in sections], "changed_files": []}]}
    store.cache_put("docs", doc)
    log.info("docs: generated %d sections for %s", len(sections), store.repo_id)
    return with_status(store, doc)


def with_status(store: RepoStore, doc: dict) -> dict:
    """Annotate each section with stale/fresh against the current snapshot."""
    h = _hashes(store)
    stale = 0
    for s in doc["sections"]:
        changed = [f for f, old in s.get("sources", {}).items() if h.get(f) != old]
        s["stale"] = bool(changed)
        s["changed_files"] = changed
        stale += bool(changed)
    doc["stale_count"] = stale
    doc["fresh"] = stale == 0
    return doc


def get_docs(store: RepoStore) -> dict | None:
    doc = store.cache_get("docs")
    return with_status(store, doc) if doc else None


def refresh_docs(store: RepoStore, llm_override: dict | None = None,
                 changed_files: list[str] | None = None) -> dict:
    """Regenerate only the stale sections; record what changed and why."""
    from .overview import build_overview
    override = {k: v for k, v in (llm_override or {}).items() if v is not None}
    doc = get_docs(store)
    if not doc:
        return generate_docs(store, override)
    stale = [s for s in doc["sections"] if s["stale"]]
    if not stale:
        log.info("docs: refresh requested but every section is fresh")
        return doc
    ov = build_overview(store, override)
    briefs = {sid: (t, b) for sid, t, b in SECTIONS}
    updated = []
    for i, s in enumerate(doc["sections"]):
        if s["stale"]:
            t, b = briefs.get(s["id"], (s["title"], s["title"]))
            doc["sections"][i] = _write_section(store, s["id"], t, b, ov, override, s["changed_files"])
            doc["sections"][i]["previous_markdown"] = s["markdown"]
            updated.append(s["id"])
    doc["changelog"].append({"at": time.time(), "event": "refreshed", "sections": updated,
                             "changed_files": sorted({f for s in stale for f in s["changed_files"]}
                                                     | set(changed_files or []))[:50]})
    doc["snapshot"] = store.snapshot_hash
    store.cache_put("docs", {k: v for k, v in doc.items() if k not in ("stale_count", "fresh")})
    log.info("docs: refreshed %d stale section(s): %s", len(updated), updated)
    return with_status(store, doc)


def docs_markdown(doc: dict) -> str:
    out = [f"# Onboarding guide — {doc.get('repo', '')}", "",
           f"_Generated by Sherpa from the code; every claim cites `file:line`._", ""]
    for s in doc["sections"]:
        out += [f"## {s['title']}", "", s["markdown"], ""]
    return "\n".join(out)


def check_freshness(store: RepoStore, docs_markdown_text: str) -> dict:
    """Check a user's own docs against the snapshot: unknown paths + unmatched headings."""
    heads = re.findall(r"^#{1,3}\s+(.+)$", docs_markdown_text, re.M)
    stale = []
    for h in heads[:15]:
        hits = retrieve(store, h, k=2)
        if not hits or hits[0][1] < 0.08:
            stale.append({"heading": h, "reason": "No closely matching code found in the current snapshot.",
                          "suggested_update": f"Verify '{h}' against the code; update or remove it."})
    files = set(store.files())
    for m in re.finditer(r"`([a-zA-Z0-9_./-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|md|json|yml|yaml|toml))`",
                         docs_markdown_text):
        p = m.group(1)
        if p not in files and not any(f.endswith("/" + p.lstrip("./")) for f in files):
            stale.append({"heading": p, "reason": "Referenced file not in repo snapshot.",
                          "suggested_update": f"Update the path or remove the reference to `{p}`."})
    return {"stale_sections": stale[:15], "fresh": len(stale) == 0}
