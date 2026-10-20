"""Grounded Q&A — plan → retrieve → read → synthesize → verify_citations.

If no LLM is configured (or every model fails) the offline extractive composer
answers from the retrieved chunks, so the product still works with zero setup.
"""
import logging
from typing import List, Tuple

from ..chunk import Chunk
from ..llm import LLMError, llm
from ..retrieval import expand_aliases, retrieve
from ..store import RepoStore
from .common import (SYSTEM_PROMPT, dedupe_hits, expand_by_imports, format_context, ref,
                     verify_citations)

log = logging.getLogger(__name__)

# re-exported for callers/tests that import the agents from one place
from .overview import build_overview, get_analysis  # noqa: E402,F401
from .tasks import suggest_starter_tasks  # noqa: E402,F401
from .tour import build_tour  # noqa: E402,F401
from .docs import check_freshness  # noqa: E402,F401


def _offline_qa(question: str, hits: List[Tuple[Chunk, float]]) -> str:
    if not hits:
        return ("I couldn't find relevant code for this question in the indexed snapshot.\n\n"
                "**Try next:** rephrase with names you expect in the code (a route, class or "
                "file name), or re-index the repository.")
    top = hits[0][0]
    lines = [f"The most relevant code for _{question.strip()}_ starts in `{top.file}` "
             f"{ref(top.file, top.start_line, top.end_line)}.", "",
             "**Evidence**"]
    for c, _ in hits[:5]:
        first = next((ln.strip() for ln in c.text.splitlines() if ln.strip()), "")[:100]
        lines.append(f"- `{c.file}` — `{first}` {ref(c.file, c.start_line, c.end_line)}")
    lines += ["", "**Try next**",
              f"- Read {ref(top.file, top.start_line, top.end_line)} end to end, then follow its imports.",
              "- Build a guided tour for this flow from the **Code Tour** tab.", "",
              "> _Offline mode: no language model was available, so this is an extractive "
              "answer built directly from the best-matching code._"]
    return "\n".join(lines)


def _repo_map(store: RepoStore) -> str:
    try:
        a = get_analysis(store)
    except Exception as e:  # noqa: BLE001 — the map is a hint, never fatal
        log.warning("ask: repo map unavailable (%s)", e)
        return ""
    rows = [f"- {k}/ ({len(v)} files)" for k, v in list(a.components.items())[:14]]
    ent = [f"- entrypoint {f}:{ln} ({why})" for f, ln, why in a.entrypoints[:5]]
    return "Repository map (for orientation; cite code, not this list):\n" + "\n".join(rows + ent)


def _gather(store: RepoStore, question: str, k: int) -> List[Tuple[Chunk, float]]:
    hits = retrieve(store, expand_aliases(question), k)
    # one hop along the import graph: pull in what the best files depend on
    try:
        a = get_analysis(store)
        hits = dedupe_hits(hits + expand_by_imports(store, a.edges, hits, question,
                                                     top=4, per_file=1, limit=4))
    except Exception as e:  # noqa: BLE001
        log.warning("ask: import-graph expansion skipped (%s)", e)
    return hits


SPOKEN_FORMAT = (
    "FORMAT (this answer is read aloud in a voice conversation):\n"
    "Answer in 2-5 short, plain sentences, the way you'd explain it to a colleague out loud. "
    "No headings, lists, tables or code blocks; name identifiers in plain words. "
    "End with a short question offering to go deeper.\n"
)
WRITTEN_FORMAT = (
    "FORMAT (GitHub markdown):\n"
    "1. Start with a direct 2-4 sentence answer.\n"
    "2. A '**How it works**' section: numbered steps or bullets in execution order.\n"
    "3. A '**Try next**' line with one concrete follow-up.\n"
    "Use `inline code` for identifiers, short ```lang fenced``` snippets only if essential.\n"
)


def _llm_prompt(question: str, ctx: str, repo_map: str, history: list, spoken: bool = False) -> str:
    convo = ""
    if history:
        turns = []
        for h in history[-6:]:
            role = "User" if h.get("role") == "user" else "Sherpa"
            turns.append(f"{role}: {str(h.get('text', ''))[:600]}")
        convo = "Conversation so far (for follow-up context):\n" + "\n".join(turns) + "\n\n"
    return (
        f"{convo}Question: {question}\n\n{repo_map}\n\nCode context:\n{ctx}\n\n"
        + (SPOKEN_FORMAT if spoken else WRITTEN_FORMAT) +
        "CITATIONS (mandatory): every factual sentence or bullet ends with one or more "
        "citations copied from a '--- path:start-end ---' header above, or a narrower range "
        "inside it, e.g. [backend/app/api/routes/users.py:40-58]. Never invent paths or line "
        "numbers, never write placeholders like [file:L1-L2]. If the context is insufficient, "
        "say \"I couldn't find this in the indexed code\" and suggest where to look."
    )


def answer_question(store: RepoStore, question: str, k: int = 10,
                    llm_override: dict | None = None, history: list | None = None,
                    spoken: bool = False) -> dict:
    hits = _gather(store, question, k)
    if not hits:
        log.info("ask: retrieval returned no chunks for repo=%s", store.repo_id)
    override = {k_: v for k_, v in (llm_override or {}).items() if v is not None}
    draft, mode, model = "", "offline", None
    if llm.can_use(override) and hits:
        prompt = _llm_prompt(question, format_context(hits), _repo_map(store), history or [], spoken)
        try:
            draft = llm.complete(SYSTEM_PROMPT, prompt, **override)
            mode, model = "llm", override.get("model") or llm.model
            _, cites0, _ = verify_citations(store, draft)
            if not cites0:
                log.info("ask: LLM draft had no valid citations; retrying once")
                try:
                    draft2 = llm.complete(SYSTEM_PROMPT, prompt + (
                        "\n\nYour previous answer had NO valid citations and was rejected:\n"
                        f"{draft[-2500:]}\n\nRewrite it so every claim ends with a citation "
                        "copied from the context headers."), **override)
                    _, cites2, _ = verify_citations(store, draft2)
                    log.info("ask: citation retry produced %d citations", len(cites2))
                    if cites2:
                        draft = draft2
                except LLMError as e:
                    log.warning("ask: citation retry failed (%s); keeping first draft", e)
        except LLMError as e:
            log.warning("ask: FALLBACK to offline extractive answer (%s)", e)
            draft = ""
    elif not llm.can_use(override):
        log.info("ask: no LLM configured (LLM_PROVIDER=%s); using offline composer", llm.provider)
    if not draft:
        draft, mode = _offline_qa(question, hits), "offline"

    clean, citations, dropped = verify_citations(store, draft)
    if dropped:
        log.info("ask: removed %d unverifiable citation(s): %s", len(dropped), dropped[:5])
    if mode == "llm" and not citations:
        clean += ("\n\n> ⚠️ _This answer has no verifiable code citations — treat it as "
                  "unconfirmed and check the sources below._")
    if citations:
        confidence = min(0.95, 0.5 + 0.08 * len(citations)) * (0.85 if dropped else 1.0)
    else:
        confidence = 0.25
    log.info("ask: answered mode=%s model=%s chunks=%d citations=%d dropped=%d",
             mode, model, len(hits), len(citations), len(dropped))
    sources = citations or [
        {"file": c.file, "start_line": c.start_line, "end_line": c.end_line,
         "snippet": c.text[:1200]} for c, _ in hits[:3]]
    return {"answer_markdown": clean.strip(), "citations": sources,
            "confidence": round(confidence, 2), "mode": mode, "model": model,
            "verify": {"grounded": bool(citations) and not dropped,
                       "verified": len(citations), "unchecked_claims": dropped}}
