"""Guided tours — "what happens when a user signs up", step by step.

Candidates come from hybrid retrieval plus one hop along the import graph. The
LLM orders them into an execution path and explains each stop; it can only pick
candidate chunks (and narrow line ranges inside their files), so every step is real code.
"""
from ..tracing import traced
import logging
import re

from ..analysis import is_code
from ..chunk import Chunk
from ..llm import LLMError, llm
from ..retrieval import expand_aliases, retrieve
from ..store import RepoStore
from .common import (SYSTEM_PROMPT, dedupe_hits, expand_by_imports, follow_calls, format_context,
                     verify_text)

log = logging.getLogger(__name__)

FLOW_KEYWORDS = {
    "signup": ["signup", "register", "create user", "sign_up", "sign-up"],
    "login": ["login", "signin", "authenticate", "token", "session"],
    "checkout": ["checkout", "cart", "order", "payment"],
    "upload": ["upload", "multipart", "s3", "presign"],
}
MAX_STEP_LINES = 45
_CAND = re.compile(r"`?\b(?:candidate\s+)?C\d{1,2}\b`?", re.I)


def _lang(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {"py": "python", "ts": "typescript", "tsx": "tsx", "js": "javascript", "jsx": "jsx",
            "go": "go", "rs": "rust", "java": "java", "md": "markdown", "json": "json",
            "yml": "yaml", "yaml": "yaml", "sh": "bash", "rb": "ruby", "php": "php"}.get(ext, ext)


def _candidates(store: RepoStore, flow: str) -> tuple[list[Chunk], dict[int, int]]:
    """Candidate chunks, plus {callee index: caller index} for calls the tour can follow."""
    from .overview import get_analysis
    # two views of the flow: plain (finds the feature code) + route-biased (finds the entry)
    hits = dedupe_hits(retrieve(store, expand_aliases(flow), 10)
                       + retrieve(store, expand_aliases(f"{flow} route handler endpoint"), 8))
    code = ([(c, s) for c, s in hits if is_code(c.file)] or hits)[:12]
    calls: list = []
    try:
        a = get_analysis(store)
        # follow the best chunks into the functions they call (route → crud → model)
        calls = follow_calls(store, a.edges, [c for c, _ in code], flow)
        extra = [(c, sc) for c, sc in expand_by_imports(store, a.edges, code, flow, top=8, limit=8)
                 if is_code(c.file)]
        code = dedupe_hits(code + extra)
    except Exception as e:  # noqa: BLE001
        log.warning("tour: import-graph expansion skipped (%s)", e)
    # place each callee right after its caller so the model sees the hand-off
    key = lambda c: (c.file, c.start_line)  # noqa: E731
    moved = {key(callee) for _, callee in calls}
    cands = [c for c, _ in code[:20] if key(c) not in moved]
    for caller_i, callee in reversed(calls):
        cands.insert(cands.index(code[caller_i][0]) + 1, callee)
    callers = {cands.index(callee): cands.index(code[caller_i][0]) for caller_i, callee in calls}
    return cands[:22], callers


def _heuristic(store: RepoStore, flow: str, cands: list[Chunk]) -> list[dict]:
    def rank(c: Chunk):
        p = c.file.lower()
        for i, keys in enumerate((("route", "router", "controller", "view", "handler", "page", "api"),
                                  ("service", "logic", "util", "helper", "auth", "crud", "core"),
                                  ("model", "schema", "entity", "db"))):
            if any(k in p for k in keys):
                return i
        return 3
    steps = []
    for c in sorted(cands[:6], key=rank):
        end = min(c.end_line, c.start_line + MAX_STEP_LINES - 1)
        first = next((ln.strip() for ln in c.text.splitlines() if ln.strip()), "")[:90]
        steps.append({"title": f"{c.file.split('/')[-1]}", "file": c.file,
                      "start_line": c.start_line, "end_line": end,
                      "explanation": f"Read lines {c.start_line}-{end}; it starts with `{first}`."})
    return steps


@traced("tour")
def build_tour(store: RepoStore, flow: str, llm_override: dict | None = None) -> dict:
    override = {k: v for k, v in (llm_override or {}).items() if v is not None}
    cands, callers = _candidates(store, flow)
    mode, raw = "offline", None
    if cands and llm.can_use(override):
        labelled = "\n\n".join(
            f"[C{i + 1}]" + (f" (called from C{callers[i] + 1})" if i in callers else "") + " "
            + format_context([(c, 0)], 2400, numbered=True) for i, c in enumerate(cands))
        prompt = (
            f"Flow to explain: \"{flow}\"\n\nCandidate code (line-numbered):\n{labelled}\n\n"
            "Build a guided tour that follows this flow in EXECUTION ORDER (entry point / UI or "
            "route → validation → business logic → data layer → response). Prefer the function that "
            "actually handles the flow over setup/boilerplate (imports, router declarations), and include "
            "the data-layer step (crud/model/repository) when a candidate shows it. When a step's code "
            "calls a function shown in a candidate marked \"called from\" that step, continue the tour "
            "into it — don't stop at the endpoint if the work happens one call deeper. Skip unrelated "
            "candidates. Return JSON:\n"
            '{"title": "short title", "summary": "2-3 sentence markdown overview with citations",\n'
            ' "steps": [{"candidate": "C3", "title": "what happens here (max 8 words)", '
            '"start_line": 40, "end_line": 62, "explanation": "2-4 sentences of markdown: what this '
            'code does, why it matters, what it hands off to next. Use `inline code` for names."}],\n'
            ' "next_questions": ["a follow-up question a newcomer could ask"]}\n'
            f"4-7 steps. start_line/end_line must lie inside the candidate's numbered lines, at most "
            f"{MAX_STEP_LINES} lines. Citations in summary use [path:start-end] from the headers. "
            "Never mention candidate labels like C3 in prose — name files and functions instead.")
        try:
            raw = llm.complete_json(SYSTEM_PROMPT, prompt, max_tokens=3000, **override)
            mode = "llm"
        except (LLMError, ValueError) as e:
            log.warning("tour: FALLBACK to heuristic tour (%s)", e)

    cites: list = []
    dropped: list = []
    steps = []
    if raw:
        for s in raw.get("steps", []):
            try:
                c = cands[int(str(s.get("candidate", "")).lstrip("Cc")) - 1]
            except (ValueError, IndexError, TypeError):
                log.info("tour: dropped step with unknown candidate %r", s.get("candidate"))
                continue
            n = len(store.lines(c.file))
            try:
                s1, s2 = int(s.get("start_line")), int(s.get("end_line"))
            except (TypeError, ValueError):
                s1, s2 = c.start_line, c.end_line
            if not (1 <= s1 <= s2 <= n):
                s1, s2 = c.start_line, c.end_line
            s2 = min(s2, s1 + MAX_STEP_LINES - 1, n)
            steps.append({"title": str(s.get("title", ""))[:80] or c.file.split("/")[-1],
                          "file": c.file, "start_line": s1, "end_line": s2,
                          "explanation": verify_text(store, _CAND.sub("this code", str(s.get("explanation", ""))),
                                                     cites, dropped)})
        if len(steps) < 2:
            log.warning("tour: LLM returned %d usable steps; FALLBACK to heuristic", len(steps))
            mode, raw, steps = "offline", None, []
    if not steps:
        steps = _heuristic(store, flow, cands)

    out_steps = []
    for i, s in enumerate(steps, 1):
        code = store.read(s["file"], s["start_line"], s["end_line"])
        out_steps.append({**s, "code": code, "language": _lang(s["file"]),
                          "caption": f"Step {i}: {s['title']}"})
        cites.append({"file": s["file"], "start_line": s["start_line"],
                      "end_line": s["end_line"], "snippet": code[:1200]})
    summary = verify_text(store, str((raw or {}).get("summary", "")), cites, dropped)
    log.info("tour: flow=%r mode=%s steps=%d", flow, mode, len(out_steps))
    return {"title": str((raw or {}).get("title") or f"Guided tour: {flow}")[:100],
            "flow": flow, "summary": summary,
            "estimated_minutes": 3 + 2 * len(out_steps), "steps": out_steps,
            "next_questions": [str(q)[:160] for q in (raw or {}).get("next_questions", [])][:3],
            "mode": mode, "model": (override.get("model") or llm.model) if mode == "llm" else None,
            "dropped": dropped}
