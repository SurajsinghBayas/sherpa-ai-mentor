"""Grounded Q&A — plan → retrieve → read → synthesize → verify_citations.

If no LLM is configured (or every model fails) the offline extractive composer
answers from the retrieved chunks, so the product still works with zero setup.
"""
import logging
from typing import List, Tuple

from ..chunk import Chunk
from ..history import get_history
from ..llm import LLMError, llm
from ..retrieval import expand_aliases, retrieve
from ..store import RepoStore
from .commits import asks_history, file_facts, format_commits, named_files, relevant, verify_commits
from .common import (SYSTEM_PROMPT, dedupe_hits, expand_by_imports, format_context, ref,
                     verify_citations)

log = logging.getLogger(__name__)

# re-exported for callers/tests that import the agents from one place
from .overview import build_overview, get_analysis  # noqa: E402,F401
from .tasks import suggest_starter_tasks  # noqa: E402,F401
from .tour import build_tour  # noqa: E402,F401
from .docs import check_freshness  # noqa: E402,F401


def _offline_commits(picked: list) -> str:
    rows = [f"- {c['subject']} [commit {c['sha'][:7]}]" for c in picked[:6]]
    return "**Related commits**\n" + "\n".join(rows) if rows else ""


def _offline_qa(question: str, hits: List[Tuple[Chunk, float]], picked: list | None = None) -> str:
    if not hits and picked:
        return _offline_commits(picked) + ("\n\n> _Offline mode: no language model was available, so "
                                           "these are the commits that match your question._")
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
    if picked:
        lines += ["", _offline_commits(picked)]
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
    "No headings, lists, tables, code blocks or 'Evidence' section; name identifiers in plain words. "
    "End with a short question offering to go deeper.\n"
)
WRITTEN_FORMAT = (
    "FORMAT (GitHub markdown, shown in a chat panel):\n"
    "1. Open with a direct 2-4 sentence answer, with no heading or label before it.\n"
    "2. Then the line **How it works** (bold, exactly that), followed by 3-6 numbered steps in "
    "execution order, one or two sentences each.\n"
    "3. End with **Try next:** and one concrete follow-up on the same line.\n"
    "Never use # headings, tables or horizontal rules, and no other sections (no 'Evidence' or "
    "'Summary'). Each citation goes at the end of the sentence or step it supports, on the same "
    "line, never on a line of its own or as a sub-bullet. Use `inline code` for identifiers and "
    "short ```lang fenced``` snippets only if essential. Keep it under about 220 words.\n"
)


COMMIT_RULE = (
    " Statements about history (when something was added or changed, who changed it, what changed "
    "recently) cite the commit instead, e.g. [commit 1a2b3c4], copied from the commit history list. "
    "A commit's author is the name after 'by' on that commit's own line: never credit a commit to "
    "anyone else, and never invent ids, dates or authors. Refer to people by name (or 'they'), "
    "never 'he' or 'she'; bots such as dependabot[bot] are automated tools, not people.")
NO_HISTORY = ("Commit history: not available for this source (an upload, or a repo Sherpa can't "
              "clone again). If the question needs history, say so briefly and answer from the code.")


def _llm_prompt(question: str, ctx: str, repo_map: str, history: list, spoken: bool = False,
                commits: str = "") -> str:
    convo = ""
    if history:
        turns = []
        for h in history[-6:]:
            role = "User" if h.get("role") == "user" else "Sherpa"
            turns.append(f"{role}: {str(h.get('text', ''))[:600]}")
        convo = "Conversation so far (for follow-up context):\n" + "\n".join(turns) + "\n\n"
    return (
        f"{convo}Question: {question}\n\n{repo_map}\n\n" + (f"{commits}\n\n" if commits else "")
        + f"Code context:\n{ctx or '(no matching code)'}\n\n"
        + (SPOKEN_FORMAT if spoken else WRITTEN_FORMAT) +
        "CITATIONS (mandatory): every factual sentence or bullet ends with one or more "
        "citations copied from a '--- path:start-end ---' header above, or a narrower range "
        "inside it, e.g. [backend/app/api/routes/users.py:40-58]. Never invent paths or line "
        "numbers, never write placeholders like [file:L1-L2]. If the context is insufficient, "
        "say \"I couldn't find this in the indexed code\" and suggest where to look."
        + (COMMIT_RULE if commits and commits != NO_HISTORY else "")
    )


def answer_question(store: RepoStore, question: str, k: int = 10,
                    llm_override: dict | None = None, history: list | None = None,
                    spoken: bool = False) -> dict:
    hits = _gather(store, question, k)
    if not hits:
        log.info("ask: retrieval returned no chunks for repo=%s", store.repo_id)
    hist, picked, commits_ctx = None, [], ""
    if asks_history(question):
        try:
            hist = get_history(store)
        except Exception as e:  # noqa: BLE001 — history is extra context, never fatal
            log.warning("ask: commit history unavailable (%s)", e)
        if hist and hist.get("commits"):
            hit_files = list(dict.fromkeys(c.file for c, _ in hits))
            picked = relevant(hist, question, hit_files)
            about = named_files(question, store.files(), hit_files)
            commits_ctx = format_commits(hist, picked, file_facts(hist, about))
        else:
            commits_ctx = NO_HISTORY
    override = {k_: v for k_, v in (llm_override or {}).items() if v is not None}
    draft, mode, model = "", "offline", None

    def cited(text: str) -> bool:
        return bool(verify_citations(store, text)[1] or verify_commits(text, hist, store.meta)[1])

    if llm.can_use(override) and (hits or picked):
        prompt = _llm_prompt(question, format_context(hits), _repo_map(store), history or [], spoken,
                             commits_ctx)
        try:
            draft = llm.complete(SYSTEM_PROMPT, prompt, **override)
            mode, model = "llm", override.get("model") or llm.model
            if not cited(draft):
                log.info("ask: LLM draft had no valid citations; retrying once")
                try:
                    draft2 = llm.complete(SYSTEM_PROMPT, prompt + (
                        "\n\nYour previous answer had NO valid citations and was rejected:\n"
                        f"{draft[-2500:]}\n\nRewrite it so every claim ends with a citation "
                        "copied from the context headers."), **override)
                    ok = cited(draft2)
                    log.info("ask: citation retry %s", "fixed it" if ok else "still uncited")
                    if ok:
                        draft = draft2
                except LLMError as e:
                    log.warning("ask: citation retry failed (%s); keeping first draft", e)
        except LLMError as e:
            log.warning("ask: FALLBACK to offline extractive answer (%s)", e)
            draft = ""
    elif not llm.can_use(override):
        log.info("ask: no LLM configured (LLM_PROVIDER=%s); using offline composer", llm.provider)
    if not draft:
        draft, mode = _offline_qa(question, hits, picked), "offline"

    clean, citations, dropped = verify_citations(store, draft)
    clean, commit_refs, dropped_commits = verify_commits(clean, hist, store.meta)
    dropped += dropped_commits
    if dropped:
        log.info("ask: removed %d unverifiable citation(s): %s", len(dropped), dropped[:5])
    if mode == "llm" and not citations and not commit_refs:
        clean += ("\n\n> ⚠️ _This answer has no verifiable code citations — treat it as "
                  "unconfirmed and check the sources below._")
    if citations or commit_refs:
        confidence = min(0.95, 0.5 + 0.08 * (len(citations) + len(commit_refs))) * (0.85 if dropped else 1.0)
    else:
        confidence = 0.25
    log.info("ask: answered mode=%s model=%s chunks=%d citations=%d commits=%d/%d dropped=%d",
             mode, model, len(hits), len(citations), len(commit_refs), len(picked), len(dropped))
    sources = citations or [
        {"file": c.file, "start_line": c.start_line, "end_line": c.end_line,
         "snippet": c.text[:1200]} for c, _ in hits[:3]]
    return {"answer_markdown": clean.strip(), "citations": sources, "commits": commit_refs,
            "confidence": round(confidence, 2), "mode": mode, "model": model,
            "verify": {"grounded": bool(citations or commit_refs) and not dropped,
                       "verified": len(citations) + len(commit_refs), "unchecked_claims": dropped}}
