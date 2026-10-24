"""Starter tasks — first-contribution ideas grounded in concrete code signals.

Signals (TODO/FIXME, untested modules, long functions, missing docstrings) are found
statically; the LLM picks a diverse set and writes the steps. Every task points
at real file:line ranges, so a newcomer can open them immediately.
"""
from ..tracing import traced
import logging

from ..analysis import task_signals
from ..llm import LLMError, llm
from ..store import RepoStore
from .common import SYSTEM_PROMPT, check_ref, numbered, verify_text

log = logging.getLogger(__name__)

TEMPLATES = {
    "todo": ("Resolve a {detail_short} note", "easy",
             "The maintainers already flagged this — a scoped, welcome first PR.",
             ["Read the surrounding function and its callers", "Implement the smallest fix the note asks for",
              "Add or update a test that covers it", "Open a PR referencing the TODO"]),
    "untested": ("Add tests for `{stem}`", "easy",
                 "Writing tests is the fastest way to learn what a module promises.",
                 ["Read the module's public functions", "Find the project's test runner and an existing test to copy",
                  "Write one happy-path and one edge-case test", "Run the suite and open a PR"]),
    "missing_docstring": ("Document `{name}`", "easy",
                          "Docs work forces you to understand inputs, outputs and side effects.",
                          ["Read the function and trace one caller", "Write a docstring: purpose, args, returns, raises",
                           "Run the linter / tests", "Open a small PR"]),
    "long_function": ("Extract a helper from `{name}`", "medium",
                      "A safe refactor teaches the module's internals; tests keep you honest.",
                      ["Run the existing tests first", "Pick one cohesive block and extract it",
                       "Keep behaviour identical; re-run tests", "Open a PR explaining the extraction"]),
}


def _fallback(store: RepoStore, sigs: list[dict]) -> list[dict]:
    tasks, kinds = [], set()
    for s in sigs:
        if s["kind"] in kinds and len(tasks) < 3:
            continue
        title, diff, why, steps = TEMPLATES[s["kind"]]
        name = s["detail"].split("`")[1] if "`" in s["detail"] else s["file"].split("/")[-1]
        tasks.append({"title": title.format(detail_short=s["detail"].split(":")[0].lower(),
                                            stem=s["file"].split("/")[-1], name=name),
                      "why": f"{why} {s['detail']}.", "difficulty": diff,
                      "estimated_time": "1-2 hours" if diff == "easy" else "half a day",
                      "steps": steps, "skills": [],
                      "files": [{"file": s["file"], "start_line": s["start_line"], "end_line": s["end_line"]}]})
        kinds.add(s["kind"])
        if len(tasks) >= 5:
            break
    return tasks


@traced("starter_tasks")
def suggest_starter_tasks(store: RepoStore, level: str = "beginner",
                          llm_override: dict | None = None, refresh: bool = False) -> dict:
    override = {k: v for k, v in (llm_override or {}).items() if v is not None}
    cached = store.cache_get("tasks")
    if cached and not refresh and cached.get("snapshot") == store.snapshot_hash \
            and cached.get("level") == level and (cached.get("mode") == "llm" or not llm.can_use(override)):
        return cached
    from .overview import get_analysis
    sigs = task_signals(store, get_analysis(store))
    mode, tasks = "offline", []
    if sigs and llm.can_use(override):
        listing = "\n\n".join(
            f"[T{i + 1}] {s['kind']} — {s['detail']}\n--- {s['file']}:{s['start_line']}-{s['end_line']} ---\n"
            + numbered(store, s["file"], s["start_line"], min(s["end_line"], s["start_line"] + 12))
            for i, s in enumerate(sigs))
        prompt = (
            f"Newcomer level: {level}.\nCode signals found by static analysis:\n\n{listing}\n\n"
            "Pick 5 DIVERSE starter tasks (different files and kinds) a newcomer could finish in a "
            "first PR. Prefer meaningful work (tests for real logic, resolving TODOs, small refactors) "
            "over trivia; at most ONE documentation-only task. Return JSON:\n"
            '{"tasks": [{"signal": "T2", "title": "imperative, max 10 words", '
            '"why": "1-2 sentences: why this is a good first task and what it teaches, with a citation", '
            '"difficulty": "easy|medium", "estimated_time": "e.g. 1-2 hours", '
            '"steps": ["4-6 concrete steps naming real files/functions"], '
            '"skills": ["2-3 things they will learn"], '
            '"files": [{"file": "path", "start_line": 1, "end_line": 20}]}]}\n'
            "Citations look like [path:start-end] using the headers above.")
        try:
            raw = llm.complete_json(SYSTEM_PROMPT, prompt, max_tokens=3000, **override)
            cites, dropped = [], []
            for t in raw.get("tasks", [])[:6]:
                if not isinstance(t, dict) or not t.get("title"):
                    continue
                refs = []
                for f in t.get("files", []):
                    if isinstance(f, dict):
                        c = check_ref(store, f.get("file"), f.get("start_line", 1),
                                      f.get("end_line", f.get("start_line", 1)))
                        if c:
                            refs.append({k: c[k] for k in ("file", "start_line", "end_line")})
                try:
                    sig = sigs[int(str(t.get("signal", "")).lstrip("Tt")) - 1]
                except (ValueError, IndexError):
                    sig = None
                if sig and not any(r["file"] == sig["file"] for r in refs):
                    refs.insert(0, {"file": sig["file"], "start_line": sig["start_line"],
                                    "end_line": sig["end_line"]})
                if not refs:
                    log.info("tasks: dropped ungrounded task %r", t.get("title"))
                    continue
                tasks.append({"title": str(t["title"])[:100],
                              "why": verify_text(store, str(t.get("why", "")), cites, dropped),
                              "difficulty": "medium" if str(t.get("difficulty")).lower() == "medium" else "easy",
                              "estimated_time": str(t.get("estimated_time", ""))[:40],
                              "steps": [verify_text(store, str(x), cites, dropped) for x in t.get("steps", [])][:7],
                              "skills": [str(x)[:60] for x in t.get("skills", [])][:4],
                              "files": refs[:4]})
            if len(tasks) >= 2:
                mode = "llm"
            else:
                log.warning("tasks: LLM produced %d grounded tasks; FALLBACK to templates", len(tasks))
                tasks = []
        except (LLMError, ValueError) as e:
            log.warning("tasks: FALLBACK to template tasks (%s)", e)
    if not tasks:
        tasks = _fallback(store, sigs)
    if not tasks:
        files = [f for f in store.files() if not f.startswith("web/")][:2]
        tasks = [{"title": "Improve the README's setup section", "why": "Docs are the safest first PR.",
                  "difficulty": "easy", "estimated_time": "1 hour", "skills": [],
                  "steps": ["Follow the setup steps yourself", "Fix anything that was unclear", "Open a PR"],
                  "files": [{"file": f, "start_line": 1, "end_line": min(20, len(store.lines(f)))} for f in files]}]
    out = {"tasks": tasks, "mode": mode, "level": level, "signals_found": len(sigs),
           "model": (override.get("model") or llm.model) if mode == "llm" else None,
           "snapshot": store.snapshot_hash}
    log.info("tasks: mode=%s tasks=%d signals=%d", mode, len(tasks), len(sigs))
    store.cache_put("tasks", out)
    return out
