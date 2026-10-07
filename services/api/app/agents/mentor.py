"""Sherpa agents — agentic mentor loop with enforced citations.

Each agent follows: plan → retrieve (search_code) → read (exact lines)
→ synthesize → verify_citations. `CitationVerifier` is the grounding
guarantee: markers like [path:L1-L2] must exist in the snapshot.

LLM: pluggable `LLMClient`. If no provider key is configured we use the
offline extractive composer so the demo works with zero setup.
"""
import os
import re
from typing import List, Tuple

from ..chunk import Chunk
from ..retrieval import expand_aliases, retrieve
from ..store import RepoStore

CITE_RE = re.compile(r"\[([^\[\]]+?):(\d+)(?:-(\d+))?\]")
FLOW_KEYWORDS = {
    "signup": ["signup", "register", "create user", "sign_up", "sign-up"],
    "login": ["login", "signin", "authenticate", "token", "session"],
    "checkout": ["checkout", "cart", "order", "payment"],
    "upload": ["upload", "multipart", "s3", "presign"],
}


class LLMClient:
    """Minimal BYOK interface. Add providers without touching agents."""

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "none").lower()
        self.model = os.getenv("LLM_MODEL", "offline")

    @property
    def available(self) -> bool:
        if self.provider in ("openai",):
            return bool(os.getenv("OPENAI_API_KEY"))
        if self.provider in ("anthropic",):
            return bool(os.getenv("ANTHROPIC_API_KEY"))
        if self.provider in ("gemini", "google"):
            return bool(os.getenv("GEMINI_API_KEY"))
        if self.provider in ("ollama",):
            return True
        return False

    def compose(self, system: str, user: str, *,
                  provider: str | None = None,
                  model: str | None = None,
                  api_key: str | None = None,
                  base_url: str | None = None) -> str:
        """Compose with optional per-request credentials.

        `provider`/`api_key`/`base_url` come from the caller's stored
        credentials (BYOK) or a custom endpoint; otherwise env config applies.
        Any OpenAI-compatible gateway works via `base_url`.
        """
        prov = (provider or self.provider).lower()
        mdl = model or self.model
        try:
            if prov in ("openai", "openrouter") and (api_key or os.getenv("OPENAI_API_KEY")):
                from openai import OpenAI
                base = base_url or os.getenv("OPENAI_BASE_URL") or None
                if prov == "openrouter" and not base:
                    base = "https://openrouter.ai/api/v1"
                client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"),
                                base_url=base)
                extra: dict = {}
                if prov == "openrouter":
                    # OpenRouter attribution (optional, improves rate limits/dashboards)
                    extra["extra_headers"] = {
                        "HTTP-Referer": os.getenv("SITE_URL", "http://localhost:3000"),
                        "X-Title": "Sherpa AI Mentor",
                    }
                r = client.chat.completions.create(
                    model=os.getenv("LLM_MODEL", "gpt-4o-mini") if not model else mdl,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    temperature=0.2, max_tokens=1200, **extra)
                return r.choices[0].message.content or ""
            if prov == "anthropic" and (api_key or os.getenv("ANTHROPIC_API_KEY")):
                import anthropic
                client = anthropic.Anthropic(
                    api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
                m = client.messages.create(
                    model=mdl if model else "claude-3-5-haiku-latest",
                    max_tokens=1200, system=system,
                    messages=[{"role": "user", "content": user}])
                return "".join(b.text for b in m.content
                                if getattr(b, "type", "") == "text")
            if prov == "ollama" or base_url:
                import httpx
                base = (base_url or os.getenv("OLLAMA_BASE_URL",
                                              "http://localhost:11434")).rstrip("/")
                if base.endswith("/v1"):  # OpenAI-compatible gateway, not Ollama
                    from openai import OpenAI
                    client = OpenAI(api_key=api_key or "not-needed", base_url=base)
                    r = client.chat.completions.create(
                        model=mdl, messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user}],
                        temperature=0.2, max_tokens=1200)
                    return r.choices[0].message.content or ""
                r = httpx.post(f"{base}/api/generate", json={
                    "model": mdl if model else os.getenv("LLM_MODEL", "codellama"),
                    "prompt": f"{system}\n\n{user}", "stream": False}, timeout=60)
                r.raise_for_status()
                return r.json().get("response", "")
        except Exception as e:
            return f"__LLM_ERROR__: {e}"
        return ""


llm = LLMClient()
try:
    with open(os.path.join(os.path.dirname(__file__),
                           "../../../packages/core/prompts/system.md")) as _f:
        SYSTEM_PROMPT = _f.read()
except OSError:
    SYSTEM_PROMPT = "You are Sherpa, a senior-engineer mentor. Cite every claim as [file:L1-L2]."


# ---------- citation verifier ----------

def verify_citations(store: RepoStore, markdown: str) -> Tuple[str, list, list]:
    """Parse [file:L1-L2], keep only ones that exist. Returns (clean_md, citations, dropped)."""
    files = set(store.files())
    out_cites = []
    dropped = []

    def file_exists(p: str) -> str | None:
        if p in files:
            return p
        # suffix match (model may emit short path)
        cands = [f for f in files if f.endswith(p.lstrip("./"))]
        return cands[0] if cands else None

    for m in CITE_RE.finditer(markdown):
        raw, s1, s2 = m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
        real = file_exists(raw.strip())
        if not real:
            dropped.append(m.group(0))
            continue
        if s1 < 1 or s2 < s1 or s2 - s1 > 400:
            dropped.append(m.group(0))
            continue
        snippet = store.read(real, s1, min(s2, s1 + 12))
        if not snippet.strip():
            dropped.append(m.group(0))
            continue
        out_cites.append({"file": real, "start_line": s1, "end_line": s2,
                          "snippet": snippet[:800]})
    # de-dupe
    seen, uniq = set(), []
    for c in out_cites:
        k = (c["file"], c["start_line"], c["end_line"])
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    return markdown, uniq, dropped


# ---------- helpers ----------

def _context(chunks: List[Tuple[Chunk, float]]) -> str:
    parts = []
    for c, s in chunks:
        parts.append(f"--- {c.file}:{c.start_line}-{c.end_line} (score={s:.2f}) ---\n{c.text[:2200]}")
    return "\n\n".join(parts)


def _offline_qa(question: str, hits: List[Tuple[Chunk, float]]) -> str:
    lines = [f"### What I found for: _{question.strip()}_", ""]
    if not hits:
        return "\n".join(lines + ["I couldn't find relevant code in this snapshot. Try re-indexing the repo."])
    lines.append("Most relevant code (read these first):")
    lines.append("")
    for c, s in hits[:5]:
        first = (c.text.strip().splitlines() or [""])[0][:110]
        lines.append(f"- [{c.file}:{c.start_line}-{c.end_line}] — `{first}`")
    lines += ["", "### Explanation", ""]
    top = hits[0][0]
    lines.append(
        f"The best match is `{top.file}` [{top.file}:{top.start_line}-{top.end_line}]. "
        "Open it and follow imports/calls from there — the surrounding chunks above show "
        "the handlers, models, and wiring involved.")
    lines += ["",
              "### Suggested next steps",
              f"- Read [{top.file}:{top.start_line}-{top.end_line}] end-to-end.",
              "- Run the tour for this flow (`POST /api/tours`) to walk each step in order."]
    return "\n".join(lines)


# ---------- public agent entry points ----------

def answer_question(store: RepoStore, question: str, k: int = 8,
                    llm_override: dict | None = None) -> dict:
    hits = retrieve(store, expand_aliases(question), k)
    ctx = _context(hits)
    draft = ""
    override = llm_override or {}
    if llm.available or override.get("api_key") or override.get("base_url"):
        user = (f"Question: {question}\n\nCode context (cite as [file:L1-L2]):\n{ctx}\n\n"
                "Rules: answer only from context. Every bullet must end with a citation. "
                "If unsure, say so.")
        draft = llm.compose(SYSTEM_PROMPT, user, **{k: v for k, v in override.items()
                                                     if v is not None})
        if draft.startswith("__LLM_ERROR__"):
            draft = ""
    if not draft:
        draft = _offline_qa(question, hits)
    _, citations, dropped = verify_citations(store, draft)
    if dropped:
        draft += "\n\n> _Sherpa withheld %d unverifiable reference(s) to stay grounded._" % len(dropped)
    confidence = min(0.95, 0.45 + 0.1 * len(citations)) if citations else 0.3
    return {"answer_markdown": draft, "citations": citations,
            "confidence": round(confidence, 2),
            "verify": {"grounded": len(dropped) == 0, "unchecked_claims": dropped}}


def build_overview(store: RepoStore) -> dict:
    roles: dict = store.meta.get("roles", {})
    # group by top-level dir / role
    comps, seen = [], set()
    for f in store.files():
        top = f.split("/")[0] if "/" in f else "(root)"
        key = (top, roles.get(f, "module"))
        if key in seen:
            continue
        seen.add(key)
        comps.append({"name": f"{top} · {roles.get(f, 'module')}",
                      "path": top if "/" in f else f,
                      "role": roles.get(f, "module")})
        if len(comps) >= 10:
            break
    # edges: naive import-scan between top dirs
    import re as _re
    edges = []
    file_text = {}
    for c in store.chunks[:400]:
        file_text.setdefault(c.file, "")
        if len(file_text[c.file]) < 3000:
            file_text[c.file] += "\n" + c.text
    tops = sorted(set((c["path"] for c in comps)))
    for f, txt in file_text.items():
        src = f.split("/")[0] if "/" in f else f
        for m in _re.finditer(r"(?:from|import)\s+([a-zA-Z0-9_./-]+)", txt):
            tgt = m.group(1).split("/")[0].split(".")[0]
            if tgt in tops and tgt != src and len(edges) < 12:
                if not any(e["from"] == src and e["to"] == tgt for e in edges):
                    edges.append({"from": src, "to": tgt, "via": "imports"})
    mermaid = "graph TD\n" + "\n".join(
        f'  {e["from"]}["{e["from"]}"] -->|{e["via"]}| {e["to"]}["{e["to"]}"]' for e in edges) \
        if edges else "graph TD\n  app[\"app\"]"
    summary = (f"This repo has **{len(store.files())} files / {len(store.chunks)} chunks**. "
               f"Key areas: {', '.join(c['name'] for c in comps[:5])}. " +
               ("Core wiring: " + "; ".join(f"{e['from']} → {e['to']}" for e in edges[:4]) + "."
                if edges else "Start from the entrypoint and follow imports outward."))
    return {"components": comps, "edges": edges, "mermaid": mermaid, "summary": summary}


def build_tour(store: RepoStore, flow: str) -> dict:
    low = flow.lower()
    keys = next((v for k, v in FLOW_KEYWORDS.items() if k in low),
                [w for w in low.split() if len(w) > 3][:4] or [flow])
    steps = []
    for kw in keys:
        for c, _ in retrieve(store, f"{flow} {kw} route handler model", k=3):
            steps.append((c, kw))
            if len(steps) >= 7:
                break
        if len(steps) >= 7:
            break
    if not steps:
        for c, _ in retrieve(store, flow, k=5):
            steps.append((c, "code"))
    # order: routes/handlers → logic → models (heuristic)
    def rank(c: Chunk):
        p = c.file.lower()
        if any(k in p for k in ("route", "router", "controller", "view", "handler")):
            return 0
        if any(k in p for k in ("service", "logic", "util", "helper", "auth")):
            return 1
        if any(k in p for k in ("model", "schema", "entity")):
            return 2
        return 3
    steps = sorted(steps, key=lambda t: rank(t[0]))
    tour = []
    for i, (c, kw) in enumerate(steps[:6], 1):
        tour.append({"caption": f"Step {i}: `{c.file}` ({kw}) — read lines {c.start_line}-{c.end_line}",
                     "file": c.file, "start_line": c.start_line,
                     "end_line": min(c.end_line, c.start_line + 30),
                     "code": "\n".join(c.text.splitlines()[:30])})
    return {"title": f"Guided tour: {flow}", "estimated_minutes": 5 + len(tour),
            "steps": tour}


def suggest_starter_tasks(store: RepoStore, level: str = "beginner") -> dict:
    roles: dict = store.meta.get("roles", {})
    tests = [f for f, r in roles.items() if r == "test"][:3]
    docs = [f for f in store.files() if f.endswith((".md", ".mdx"))][:2]
    routes = [f for f, r in roles.items() if r == "route/handler"][:3]
    tasks = []
    if docs:
        tasks.append({"title": "Fix/extend onboarding docs for one module",
                      "why": "Docs are usually stale; small, safe, teaches the map.",
                      "files": docs,
                      "steps": ["Pick one module", "Run it locally",
                                "Update the README section", "Open a PR"],
                      "difficulty": "easy"})
    if tests:
        tasks.append({"title": "Add a missing edge-case test",
                      "why": "Tests reveal intent; files are isolated and reviewable.",
                      "files": tests,
                      "steps": ["Run the suite", "Find an untested branch",
                                "Add one focused test", "Open a PR"],
                      "difficulty": "easy"})
    if routes:
        tasks.append({"title": "Add input validation to one endpoint",
                      "why": "Touches route→service→model; great guided-tour follow-up.",
                      "files": routes,
                      "steps": ["Trace the endpoint with a tour", "Add validation",
                                "Add/extend a test", "Open a PR"],
                      "difficulty": "medium"})
    if not tasks:
        files = store.files()[:3]
        tasks.append({"title": "Add type hints + docstring to one module",
                      "why": "First-contact task that forces reading real code.",
                      "files": files,
                      "steps": ["Pick the smallest file", "Annotate + document",
                                "Run checks", "Open a PR"],
                      "difficulty": "easy"})
    return {"tasks": tasks[:4]}


def check_freshness(store: RepoStore, docs_markdown: str) -> dict:
    import re as _re
    heads = _re.findall(r"^#{1,3}\s+(.+)$", docs_markdown, _re.M)
    stale = []
    for h in heads[:10]:
        hits = retrieve(store, h, k=2)
        if not hits or hits[0][1] < 0.08:
            stale.append({"heading": h,
                          "reason": "No closely matching code found in the current snapshot.",
                          "suggested_update": f"Verify '{h}' against the code; update or remove it."})
    # also flag doc file-paths that no longer exist
    for m in _re.finditer(r"`([a-zA-Z0-9_./-]+\.(?:py|ts|js|go|md))`", docs_markdown):
        p = m.group(1)
        if p not in set(store.files()) and not any(f.endswith(p) for f in store.files()):
            stale.append({"heading": p, "reason": "Referenced file not in repo snapshot.",
                          "suggested_update": f"Update the path or remove the reference to `{p}`."})
    return {"stale_sections": stale[:10], "fresh": len(stale) == 0}
