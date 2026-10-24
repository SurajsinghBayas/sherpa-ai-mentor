"""Skill check: a multiple-choice quiz written from the codebase itself.

The model writes questions about where things live, what parts are responsible for and how
data moves; each answer must be explained with a citation that exists in the snapshot. A
second, independent pass then answers every question from its cited code alone, without
seeing the intended answer; questions it answers differently are dropped, so what is left is
settled by the code. Without a model, questions are built straight from static analysis
(where a function is defined, which component a file belongs to, what a file imports).

Answers never leave the server before the quiz is submitted. Quizzes are cached per snapshot;
a retake writes new questions.
"""
from ..tracing import traced
import hashlib
import logging
import random
import re
import time

from ..analysis import symbols_of
from ..llm import LLMError, llm
from ..store import RepoStore
from .common import SYSTEM_PROMPT, numbered, ref, verify_text
from .overview import _context, _key_files, get_analysis

log = logging.getLogger(__name__)

QUESTIONS = 8
KEEP_QUIZZES = 6
LETTERS = "ABCD"
DIFFICULTY = ("easy", "medium", "hard")


def _area_names(store: RepoStore, keys) -> dict[str, str]:
    ov = store.cache_get("overview") or {}
    named = {c["key"]: c["name"] for c in ov.get("components", []) if isinstance(c, dict) and "key" in c}
    return {k: named.get(k) or (k.split("/")[-1].replace("_", " ").replace("-", " ").title()
                                if k != "(root)" else "Root") for k in keys}


# ---------------------------------------------------------------- model-written questions

def _ask_model(store: RepoStore, a, n: int, avoid: list[str], override: dict) -> list[dict]:
    keys = list(a.components)
    prompt = (
        f"{_context(store, a)}\n\nCOMPONENT KEYS (use exactly): {keys}\n"
        + ("QUESTIONS ALREADY ASKED (write different ones):\n- " + "\n- ".join(avoid[-24:]) + "\n" if avoid else "")
        + f"\nWrite {n + 3} multiple-choice questions that check whether a developer new to THIS codebase "
        "understands it well enough to make a first change. Ask about: where something lives, what a "
        "module or function is responsible for, what calls what, how a request or data moves between "
        "components, what happens in a given situation. Never ask trivia (line counts, versions, exact "
        "strings, syntax, licence). Spread them across components, at most 2 per component, mixing "
        "easy, medium and hard. Wrong options must be plausible: use real names from this codebase.\n"
        "Return JSON: {\"questions\": [{\"area\": \"<exact component key>\", "
        "\"difficulty\": \"easy|medium|hard\", \"question\": \"one sentence\", "
        "\"options\": [\"4 short distinct options\"], \"answer\": <index 0-3 of the correct option>, "
        "\"explanation\": \"1-2 sentences saying why, ending with a citation that proves it\"}]}\n"
        "Citations look like [path/to/file.py:12-30] and must use paths + line numbers shown above.")
    raw = llm.complete_json(SYSTEM_PROMPT, prompt, max_tokens=4000, **override)
    return [q for q in raw.get("questions", []) if isinstance(q, dict)]


def _check_blind(store: RepoStore, qs: list[dict], override: dict) -> list[bool] | None:
    """Answer each question from its cited code alone; True where that agrees with the key."""
    blocks = []
    for i, q in enumerate(qs, 1):
        c = q["cite"]
        lo, hi = max(1, c["start_line"] - 8), min(c["end_line"] + 8, c["start_line"] + 60)
        opts = "\n".join(f"  {LETTERS[j]}. {o}" for j, o in enumerate(q["options"]))
        blocks.append(f"QUESTION {i}: {q['question']}\n{opts}\nCODE {c['file']}:{lo}-{hi}\n"
                      f"{numbered(store, c['file'], lo, hi)}")
    prompt = ("\n\n".join(blocks) + "\n\nAnswer every question using ONLY the code shown under it. "
              "If that code does not settle the answer, answer null.\n"
              'Return JSON: {"answers": [{"n": 1, "choice": "A|B|C|D or null"}]}')
    try:
        raw = llm.complete_json("You check quiz questions against source code. Be strict.",
                                prompt, max_tokens=800, **override)
    except (LLMError, ValueError) as e:
        log.warning("quiz: blind check unavailable (%s)", e)
        return None
    got = {}
    for x in raw.get("answers", []):
        if isinstance(x, dict) and isinstance(x.get("n"), int) and isinstance(x.get("choice"), str):
            ch = x["choice"].strip().upper()[:1]
            if ch in LETTERS:
                got[x["n"]] = LETTERS.index(ch)
    return [got.get(i) == q["answer"] for i, q in enumerate(qs, 1)]


def _clean(store: RepoStore, a, raw: list[dict]) -> list[dict]:
    out, seen = [], set()
    keys = set(a.components)
    for q in raw:
        text = re.sub(r"\s+", " ", str(q.get("question", ""))).strip()
        opts = [re.sub(r"\s+", " ", str(o)).strip()[:160] for o in (q.get("options") or [])]
        try:
            answer = int(q.get("answer"))
        except (TypeError, ValueError):
            continue
        if not text or text.lower() in seen or len(opts) != 4 or len({o.lower() for o in opts}) != 4 \
                or not all(opts) or not 0 <= answer < 4:
            continue
        cites, dropped = [], []
        expl = verify_text(store, str(q.get("explanation", "")), cites, dropped)
        if not cites:
            continue  # an answer the code can't back up is not asked
        cite = {k: cites[0][k] for k in ("file", "start_line", "end_line")}
        area = str(q.get("area", ""))
        if area not in keys:
            area = a.component_of(cite["file"]) or next(iter(keys))
        diff = str(q.get("difficulty", "")).lower()
        seen.add(text.lower())
        out.append({"question": text[:300], "options": opts, "answer": answer, "explanation": expl,
                    "cite": cite, "area": area, "difficulty": diff if diff in DIFFICULTY else "medium"})
    return out


# ---------------------------------------------------------------- questions from static analysis

def _offline(store: RepoStore, a, n: int, rng: random.Random, avoid: set[str]) -> list[dict]:
    names = _area_names(store, a.components)
    files = [f for fs in a.components.values() for f in fs]
    if len(files) < 4:
        return []
    ext = lambda f: f.rsplit(".", 1)[-1] if "." in f else ""  # noqa: E731
    pool: list[dict] = []

    def others(right: str, k=3, near=True) -> list[str]:
        same = [f for f in files if f != right and (not near or ext(f) == ext(right))]
        cand = same if len(same) >= k else [f for f in files if f != right]
        return rng.sample(cand, k)

    # where is X defined?
    defs: dict[str, list] = {}
    for f in files:
        for name, s, e, kind in symbols_of(store, f):
            defs.setdefault(name, []).append((f, s, e, kind))
    unique = [(name, *v[0]) for name, v in defs.items() if len(v) == 1 and len(name) >= 6
              and not name.startswith("_") and name.lower() not in ("__init__", "default")]
    rng.shuffle(unique)
    for name, f, s, e, kind in unique[:n]:
        pool.append({"question": f"Where is the {kind} `{name}` defined?",
                     "options": [f, *others(f)], "answer": 0, "difficulty": "easy",
                     "explanation": f"`{name}` is defined in `{f}` {ref(f, s, max(e, s))}.", "area": a.component_of(f)})
    # which component is this file in?
    if len(a.components) >= 4:
        for key in rng.sample(list(a.components), min(len(a.components), n)):
            f = _key_files(store, a, a.components[key], 1)[0]
            wrong = rng.sample([k for k in a.components if k != key], 3)
            end = min(len(store.lines(f)), 20) or 1
            pool.append({"question": f"Which part of the codebase does `{f}` belong to?",
                         "options": [names[key], *[names[k] for k in wrong]], "answer": 0, "difficulty": "easy",
                         "explanation": f"`{f}` is part of {names[key]} {ref(f, 1, end)}.", "area": key})
    # what does this file import?
    by_src: dict[str, list] = {}
    for e in a.edges:
        by_src.setdefault(e.src, []).append(e)
    srcs = [s for s in by_src if len({e.dst for e in by_src[s]}) >= 1]
    rng.shuffle(srcs)
    for src in srcs[:n]:
        e = rng.choice(by_src[src])
        imported = {x.dst for x in by_src[src]}
        wrong = [f for f in files if f not in imported and f != src]
        if len(wrong) < 3:
            continue
        pool.append({"question": f"Which of these files does `{src}` import code from?",
                     "options": [e.dst, *rng.sample(wrong, 3)], "answer": 0, "difficulty": "medium",
                     "explanation": f"`{src}` imports from `{e.dst}` {ref(src, e.line, e.line)}.",
                     "area": a.component_of(src)})
    # where does it start?
    if a.entrypoints:
        f, ln, why = a.entrypoints[0]
        pool.append({"question": "Where does the program start running?",
                     "options": [f, *others(f)], "answer": 0, "difficulty": "medium",
                     "explanation": f"`{f}` is the entry point ({why}) {ref(f, ln, ln + 5)}.",
                     "area": a.component_of(f)})
    rng.shuffle(pool)
    pool = [q for q in pool if q["question"].lower() not in avoid] or pool
    # one question per area first, then fill
    picked, areas = [], set()
    for q in pool:
        if q["area"] not in areas:
            picked.append(q)
            areas.add(q["area"])
    picked += [q for q in pool if q not in picked]
    return _clean(store, a, picked[:n])


# ---------------------------------------------------------------- quiz life cycle

def _public(quiz: dict) -> dict:
    """What the browser may see before the quiz is submitted: no answers, no explanations."""
    return {k: quiz[k] for k in ("id", "mode", "model", "checked", "areas", "minutes", "created_at")} | {
        "questions": [{"n": i + 1, "area": q["area"], "area_name": quiz["area_names"].get(q["area"], q["area"]),
                       "difficulty": q["difficulty"], "question": q["question"], "options": q["options"]}
                      for i, q in enumerate(quiz["questions"])]}


def _saved(store: RepoStore) -> dict:
    box = store.cache_get("quiz") or {}
    if box.get("snapshot") != store.snapshot_hash:
        box = {"snapshot": store.snapshot_hash, "quizzes": {}, "order": []}
    return box


@traced("quiz")
def build_quiz(store: RepoStore, llm_override: dict | None = None, fresh: bool = False) -> dict:
    """The latest quiz for this snapshot, or a new one (`fresh`, or none yet)."""
    override = {k: v for k, v in (llm_override or {}).items() if v is not None}
    box = _saved(store)
    if box["order"] and not fresh:
        return _public(box["quizzes"][box["order"][-1]])
    a = get_analysis(store)
    avoid = [q["question"] for qid in box["order"] for q in box["quizzes"][qid]["questions"]]
    seed = int(time.time() * 1000) ^ len(avoid)
    rng = random.Random(seed)
    mode, model, checked, qs = "offline", None, False, []
    if llm.can_use(override) and a.components:
        try:
            qs = _clean(store, a, _ask_model(store, a, QUESTIONS, avoid, override))
            mode, model = "llm", override.get("model") or llm.model
        except (LLMError, ValueError) as e:
            log.warning("quiz: FALLBACK to static questions (%s)", e)
        if qs:
            verdict = _check_blind(store, qs, override)
            if verdict is not None:
                kept = [q for q, ok in zip(qs, verdict) if ok]
                log.info("quiz: blind check kept %d of %d questions", len(kept), len(qs))
                qs, checked = kept, True
    if len(qs) < QUESTIONS:  # top up (or build entirely) from static analysis
        have = {q["question"].lower() for q in qs}
        qs += [q for q in _offline(store, a, QUESTIONS, rng, set(map(str.lower, avoid)) | have)
               if q["question"].lower() not in have][:QUESTIONS - len(qs)]
    qs = qs[:QUESTIONS]
    # the model puts most answers first: shuffle every option list
    for q in qs:
        order = list(range(4))
        rng.shuffle(order)
        q["options"] = [q["options"][j] for j in order]
        q["answer"] = order.index(q["answer"])
    area_keys = list(dict.fromkeys(q["area"] for q in qs))
    quiz = {"id": hashlib.sha1(f"{store.snapshot_hash}:{seed}".encode()).hexdigest()[:16],
            "questions": qs, "mode": mode if qs else "offline", "model": model, "checked": checked,
            "area_names": _area_names(store, area_keys),
            "areas": [{"key": k, "name": n} for k, n in _area_names(store, area_keys).items()],
            "minutes": max(2, round(len(qs) * 0.6)), "created_at": time.time()}
    box["quizzes"][quiz["id"]] = quiz
    box["order"] = (box["order"] + [quiz["id"]])[-KEEP_QUIZZES:]
    box["quizzes"] = {k: box["quizzes"][k] for k in box["order"]}
    store.cache_put("quiz", box)
    return _public(quiz)


LEVELS = ((0.8, "Ready to contribute"), (0.5, "Getting there"), (0.0, "Keep exploring"))


def grade(store: RepoStore, quiz_id: str, answers: list) -> dict | None:
    """Score a submitted quiz; None when the quiz is unknown (expired, or the repo was re-indexed)."""
    quiz = _saved(store)["quizzes"].get(quiz_id)
    if not quiz:
        return None
    results, areas = [], {}
    for i, q in enumerate(quiz["questions"]):
        chosen = answers[i] if i < len(answers) and isinstance(answers[i], int) and 0 <= answers[i] < 4 else None
        ok = chosen == q["answer"]
        a = areas.setdefault(q["area"], {"key": q["area"], "name": quiz["area_names"].get(q["area"], q["area"]),
                                         "correct": 0, "total": 0})
        a["total"] += 1
        a["correct"] += ok
        results.append({"n": i + 1, "question": q["question"], "options": q["options"], "chosen": chosen,
                        "answer": q["answer"], "correct": ok, "explanation": q["explanation"],
                        "cite": q["cite"], "area": q["area"], "difficulty": q["difficulty"]})
    correct = sum(r["correct"] for r in results)
    total = len(results)
    share = correct / total if total else 0
    area_list = sorted(areas.values(), key=lambda x: (x["correct"] / x["total"], x["name"]))
    return {"quiz_id": quiz_id, "correct": correct, "total": total, "percent": round(share * 100),
            "level": next(name for cut, name in LEVELS if share >= cut),
            "areas": area_list, "weak": [x for x in area_list if x["correct"] < x["total"]][:3],
            "results": results, "checked": quiz["checked"]}
