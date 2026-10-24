"""Pipeline machine: how an agent loop, ML pipeline or workflow actually runs.

The web app draws the result as a small isometric machine: one station per stage,
pipes for the hand-offs, a return pipe for each loop. Where the code declares the
graph (LangGraph nodes and edges, GitHub Actions jobs and `needs`, scikit-learn
`Pipeline` steps, Airflow `>>` chains) the stages and links are read straight from it;
the model only names and explains them. Otherwise the model maps the pipeline from the
code that mentions models, tools, vector stores, training or queues. Every stage cites
code that exists. Results are cached per snapshot.
"""
import logging
import re

from ..llm import LLMError, llm
from ..store import RepoStore
from .common import SYSTEM_PROMPT, check_ref, ref, verify_text

log = logging.getLogger(__name__)

# what a stage is; each type is drawn as its own machine part
TYPES = ("input", "llm", "agent", "tool", "retriever", "store", "router", "transform",
         "model", "train", "eval", "queue", "job", "output")
KINDS = ("agent", "rag", "ml", "workflow", "app")
MAX_STAGES = 12

# code that tells what kind of pipeline a repo has (term → kind)
SIGNALS = {
    "agent": ("langgraph", "stategraph", "add_node(", "crewai", "autogen", "tool_calls", "bind_tools",
              "agentexecutor", "create_react_agent", "@tool\n", "tool_choice"),
    "rag": ("embedding", "vectorstore", "vector_store", "pgvector", "faiss", "chromadb", "pinecone",
            "qdrant", "weaviate", "similarity_search", "rerank"),
    "llm": ("import openai", "from openai", "anthropic", "bedrock", "chat.completions", "messages.create",
            "chatopenai", "langchain", "llama_index", "litellm"),
    "ml": ("import torch", "tensorflow", "keras", "from sklearn", "xgboost", "lightgbm", "optimizer.step",
           "dataloader", "train_test_split", "loss.backward", "model.fit("),
    "workflow": ("from airflow", "import airflow", "from prefect", "@flow", "dagster", "celery", "kafka",
                 "rabbitmq", "temporalio", "luigi", "@shared_task"),
}
CODE = (".py", ".ts", ".tsx", ".js", ".mjs", ".go", ".rs", ".java", ".kt", ".rb", ".ipynb")


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _slug(s: str) -> str:
    if s in ("__start__", "__end__"):
        return s
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40] or "stage"


def _name(s: str) -> str:
    return s.replace("_", " ").replace("-", " ").strip().title()[:40]


def _type_guess(name: str) -> str:
    n = name.lower()
    for words, t in ((("retriev", "search", "lookup", "rag", "fetch_doc"), "retriever"),
                     (("embed", "index", "vector", "store", "save", "persist", "db", "cache"), "store"),
                     (("route", "router", "decide", "classif", "should", "branch", "check"), "router"),
                     (("tool", "action", "execute", "call_", "api", "search_web"), "tool"),
                     (("agent", "plan", "supervisor", "critic", "reflect"), "agent"),
                     (("llm", "generate", "answer", "respond", "summar", "chat", "model_call", "write"), "llm"),
                     (("train", "fit"), "train"), (("eval", "score", "metric", "test", "valid"), "eval"),
                     (("load", "ingest", "input", "read", "start", "fetch", "download", "checkout"), "input"),
                     (("queue", "publish", "enqueue", "consume", "kafka"), "queue"),
                     (("deploy", "output", "report", "end", "notify", "upload", "release"), "output"),
                     (("model", "classifier", "regressor", "estimator", "net"), "model")):
        if any(w in n for w in words):
            return t
    return "transform"


# ---------------------------------------------------------------- graphs declared in code

_NODE = re.compile(r"\.add_node\(\s*(?:[\"']([\w\- ]+)[\"']\s*(?:,\s*([\w.]+))?|([A-Za-z_]\w*)\s*[,)])")
_END = r"START|END|[\"'][\w\- ]+[\"']"
_EDGE = re.compile(rf"\.add_edge\(\s*({_END})\s*,\s*({_END})")
_COND = re.compile(r"\.add_conditional_edges\(\s*[\"']([\w\- ]+)[\"']\s*,\s*(?:#[^\n]*\n\s*)*([\w.]+)\s*"
                   r"(?:,\s*(\{[^}]*\}|\[[^\]]*\]))?", re.S)
_ENTRY = re.compile(r"\.set_entry_point\(\s*[\"']([\w\- ]+)[\"']")


def _node_id(token: str) -> str:
    t = token.strip("\"'")
    return {"START": "__start__", "END": "__end__"}.get(t, t if t in ("__start__", "__end__") else _slug(t))


def _router_targets(text: str, router: str) -> list[str]:
    """Where a router without a mapping can send control: its Literal[...] return type, else its returns."""
    m = re.search(rf"def {re.escape(router)}\([^)]*\)\s*(?:->\s*([^:]+))?:", text)
    if not m:
        return []
    if m.group(1) and "Literal" in m.group(1):
        return re.findall(r"[\"']([\w\- ]+)[\"']", m.group(1))
    body = text[m.end():m.end() + 2500].split("\ndef ")[0]
    found = re.findall(r"return\s+[\"']([\w\- ]+)[\"']|return\s+(END)\b", body)
    return list(dict.fromkeys(x or y for x, y in found))


def _langgraph(store: RepoStore) -> dict | None:
    stages: dict[str, dict] = {}
    links: list[tuple[str, str, str]] = []
    ends: dict[str, tuple] = {}  # __start__/__end__ → where the code mentions them
    for f in store.files():
        if not f.endswith((".py", ".ts", ".js")):
            continue
        text = "\n".join(store.lines(f))
        if "add_node" not in text:
            continue
        for m in _NODE.finditer(text):
            name, fn = (m.group(1), m.group(2) or "") if m.group(1) else (m.group(3), m.group(3))
            sid = _slug(name)
            ln = _line_of(text, m.start())
            stages.setdefault(sid, {"id": sid, "name": _name(name), "type": _type_guess(name + " " + fn),
                                    "cite": (f, ln, ln), "fn": fn})
        for m in _EDGE.finditer(text):
            a, b = _node_id(m.group(1)), _node_id(m.group(2))
            ln = _line_of(text, m.start())
            for e in (a, b):
                if e.startswith("__"):
                    ends.setdefault(e, (f, ln, ln))
            links.append((a, b, ""))
        for m in _COND.finditer(text):
            src, router, mapping = _slug(m.group(1)), m.group(2).split(".")[-1], m.group(3) or ""
            if mapping:
                targets = re.findall(r":\s*(END|[\"'][\w\- ]+[\"'])", mapping) or \
                    re.findall(r"[\"']([\w\- ]+)[\"']", mapping)
            else:
                targets = _router_targets(text, router)
            ln = _line_of(text, m.start())
            for t in targets:
                tid = _node_id(t)
                if tid.startswith("__"):
                    ends.setdefault(tid, (f, ln, ln + 6))
                links.append((src, tid, router))
        if (m := _ENTRY.search(text)):
            ln = _line_of(text, m.start())
            ends.setdefault("__start__", (f, ln, ln))
            links.append(("__start__", _slug(m.group(1)), ""))
    if len(stages) < 2:
        return None
    # START and END become the machine's intake and its result tray
    out = []
    if "__start__" in ends:
        out.append({"id": "__start__", "name": "Input", "type": "input", "cite": ends["__start__"], "fn": "START"})
    out += list(stages.values())
    if "__end__" in ends:
        out.append({"id": "__end__", "name": "Result", "type": "output", "cite": ends["__end__"], "fn": "END"})
    return {"kind": "agent", "source": "LangGraph", "stages": out, "links": links}


def _actions(store: RepoStore) -> dict | None:
    """The workflow file whose jobs depend on each other the most (one coherent pipeline)."""
    best = None
    for f in store.files():
        if not re.match(r"\.github/workflows/[^/]+\.ya?ml$", f):
            continue
        lines = store.lines(f)
        stages: dict[str, dict] = {}
        links: list[tuple[str, str, str]] = []
        in_jobs, job = False, None
        for i, line in enumerate(lines, 1):
            if re.match(r"^jobs:\s*$", line):
                in_jobs = True
                continue
            if in_jobs and re.match(r"^\S", line):
                in_jobs = False
            if not in_jobs:
                continue
            if (m := re.match(r"^  ([\w-]+):\s*$", line)):
                job = _slug(m.group(1))
                stages.setdefault(job, {"id": job, "name": _name(m.group(1)), "type": "job",
                                        "cite": (f, i, min(i + 20, len(lines))), "fn": ""})
            elif job and (m := re.match(r"^    needs:\s*(.*)$", line)):
                val = m.group(1).strip()
                needs = re.findall(r"[\w-]+", val) if val else []
                j = i
                while not val and j < len(lines) and re.match(r"^\s+-\s*([\w-]+)", lines[j]):
                    needs.append(re.match(r"^\s+-\s*([\w-]+)", lines[j]).group(1))
                    j += 1
                links += [(_slug(n), job, "") for n in needs]
        if len(stages) >= 2 and links and (best is None or len(links) > len(best["links"])):
            best = {"kind": "workflow", "source": f"GitHub Actions ({f.rsplit('/', 1)[-1]})",
                    "stages": list(stages.values()), "links": links}
    return best


def _sklearn(store: RepoStore) -> dict | None:
    for f in store.files():
        if not f.endswith(".py"):
            continue
        text = "\n".join(store.lines(f))
        m = re.search(r"\bPipeline\(\s*(?:steps\s*=\s*)?\[", text)
        if not m:
            continue
        body = text[m.end():m.end() + 1500]
        steps = re.findall(r"\(\s*[\"']([\w\- ]+)[\"']\s*,\s*([\w.]+)", body)
        if len(steps) < 2:
            continue
        ln = _line_of(text, m.start())
        stages = [{"id": _slug(n), "name": _name(n), "fn": cls,
                   "type": "model" if i == len(steps) - 1 else "transform", "cite": (f, ln, ln + len(steps) + 1)}
                  for i, (n, cls) in enumerate(steps)]
        links = [(a["id"], b["id"], "") for a, b in zip(stages, stages[1:])]
        return {"kind": "ml", "source": "scikit-learn Pipeline", "stages": stages, "links": links}
    return None


def _airflow(store: RepoStore) -> dict | None:
    for f in store.files():
        if not f.endswith(".py"):
            continue
        text = "\n".join(store.lines(f))
        if "airflow" not in text or ">>" not in text:
            continue
        tasks = {mm.group(1): _line_of(text, mm.start())
                 for mm in re.finditer(r"^\s*(\w+)\s*=\s*\w+(?:Operator|Sensor)\(", text, re.M)}
        tasks.update({mm.group(1): _line_of(text, mm.start())
                      for mm in re.finditer(r"@task(?:\.\w+)?(?:\([^)]*\))?\s*\n\s*def\s+(\w+)", text)})
        links = []
        for line in text.splitlines():
            if ">>" in line:
                parts = [re.findall(r"\w+", p) for p in line.split(">>")]
                for a, b in zip(parts, parts[1:]):
                    links += [(_slug(x), _slug(y), "") for x in a for y in b if x in tasks and y in tasks]
        if len(tasks) >= 2 and links:
            stages = [{"id": _slug(t), "name": _name(t), "type": _type_guess(t), "cite": (f, ln, ln + 8), "fn": ""}
                      for t, ln in tasks.items()]
            return {"kind": "workflow", "source": "Airflow DAG", "stages": stages, "links": links}
    return None


def declared_graph(store: RepoStore) -> dict | None:
    """A pipeline the code spells out, or None."""
    for find in (_langgraph, _airflow, _sklearn, _actions):
        try:
            g = find(store)
        except Exception as e:  # noqa: BLE001 — a parser miss must not break the feature
            log.warning("pipeline: %s failed (%s)", find.__name__, e)
            g = None
        if g:
            return g
    return None


# ---------------------------------------------------------------- everything else: the model maps it

def signals(store: RepoStore) -> dict[str, int]:
    """How strongly the code looks like each kind of pipeline: source files that use its libraries."""
    out = {k: 0 for k in SIGNALS}
    for f in store.files():
        if not f.endswith(CODE) or "test" in f.lower():
            continue
        low = "\n".join(store.lines(f)).lower()
        for k, terms in SIGNALS.items():
            if any(t in low for t in terms):
                out[k] += 1
    return out


def _kind(sig: dict[str, int]) -> str:
    if sig["agent"] and (sig["llm"] or sig["agent"] >= 2):  # one stray "add_node(" is not an agent
        return "agent"
    if sig["rag"] and sig["llm"]:
        return "rag"
    if sig["ml"] >= 2:
        return "ml"
    if sig["workflow"]:
        return "workflow"
    if sig["llm"]:
        return "agent"
    return "app"


def _context(store: RepoStore, declared: dict | None, limit: int = 45000) -> str:
    terms = [t for ts in SIGNALS.values() for t in ts]
    scored = []
    for c in store.chunks:
        if "/test" in c.file or c.file.startswith("test"):
            continue
        low = c.text.lower()
        hits = sum(t in low for t in terms)
        if hits:
            scored.append((hits + (c.kind == "def"), c))
    scored.sort(key=lambda t: -t[0])
    files = {s["cite"][0] for s in (declared or {}).get("stages", [])}
    chosen = [c for c in store.chunks if c.file in files][:8] + [c for _, c in scored[:24]]
    parts, seen, size = [], set(), 0
    readme = next((f for f in store.files() if f.lower() in ("readme.md", "readme.rst", "readme")), None)
    if readme:
        n = min(len(store.lines(readme)), 50)
        parts.append(f"--- {readme}:1-{n} ---\n" + "\n".join(
            f"{i:>4}| {ln}" for i, ln in enumerate(store.lines(readme)[:n], 1)))
    for c in chosen:
        if (c.file, c.start_line) in seen:
            continue
        seen.add((c.file, c.start_line))
        body = "\n".join(f"{c.start_line + i:>4}| {ln}" for i, ln in enumerate(c.text.splitlines()))
        block = f"--- {c.file}:{c.start_line}-{c.end_line} ---\n{body}"
        if size + len(block) > limit:
            break
        parts.append(block)
        size += len(block)
    return "\n\n".join(parts)


def _prompt(store: RepoStore, declared: dict | None, kind: str) -> str:
    ask = (
        "Map how this codebase's main pipeline runs, as the stations of a machine, in execution order.\n"
        f"Likely kind: {kind} (agent = LLM agent loop with tools; rag = retrieval + generation; ml = data → "
        "train → evaluate → model; workflow = jobs/tasks in a DAG; app = the main request path).\n")
    if declared:
        ask += (f"\nThe code DECLARES this graph ({declared['source']}). Keep exactly these stage ids and links; "
                "only name, type and describe them:\nSTAGES: "
                + "; ".join(f"{s['id']} ({s.get('fn') or s['type']}) at {s['cite'][0]}:{s['cite'][1]}"
                            for s in declared["stages"])
                + "\nLINKS: " + "; ".join(f"{a} -> {b}" + (f" [{lbl}]" if lbl else "")
                                          for a, b, lbl in declared["links"]) + "\n")
    return (
        f"{_context(store, declared)}\n\n{ask}\n"
        "Return JSON:\n"
        '{"kind": "agent|rag|ml|workflow|app", "title": "3-6 words, e.g. Research agent loop",\n'
        ' "summary": "2-3 sentences of markdown: what goes in, what happens, what comes out, with citations",\n'
        ' "stages": [{"id": "snake_case", "name": "1-3 words", "type": "' + "|".join(TYPES) + '",\n'
        '   "description": "1-2 sentences: what this stage does and what it hands on, ending with a citation",\n'
        '   "narration": "one short sentence to be SPOKEN while this stage runs: plain words, no file names, '
        'no code symbols, no citations"}],\n'
        ' "intro": "one spoken sentence introducing the whole pipeline, plain words",\n'
        ' "links": [{"from": "id", "to": "id", "label": "what flows, 1-3 words, e.g. tool calls"}]}\n'
        f"3-{MAX_STAGES} stages. Start with where data or a request enters, end with what comes out. "
        "A loop (an agent calling tools until done, epochs, retries) is a link back to an earlier stage. "
        "A router stage has links to each branch. Types: llm = a model call, agent = an LLM that decides "
        "what to do next, tool = something the agent calls, retriever = search over an index, store = a "
        "database/vector store/cache, router = a branch, model = an ML model, train/eval = training and "
        "evaluation, job = a CI/workflow job, queue = a queue or event bus.\n"
        "Citations look like [path/to/file.py:12-30] and must use paths + line numbers shown above.")


def _from_declared(store: RepoStore, declared: dict) -> dict:
    stages = [{"id": s["id"], "name": s["name"], "type": s["type"],
               "description": f"`{s.get('fn') or s['name']}` {ref(*s['cite'])}"} for s in declared["stages"]]
    return {"kind": declared["kind"], "title": f"{declared['source']} pipeline",
            "summary": f"This pipeline is declared with **{declared['source']}**: "
                       f"{len(stages)} stages, {len(declared['links'])} links.",
            "stages": stages,
            "links": [{"from": a, "to": b, "label": lbl} for a, b, lbl in declared["links"]]}


def _spoken(text) -> str:
    """A line meant to be heard: no citations, code marks or file paths."""
    t = re.sub(r"\[[^\]]*:\d+[^\]]*\]", "", str(text or ""))
    t = re.sub(r"[`*_#]", "", t)
    t = re.sub(r"\s+([.,;:!?])", r"\1", re.sub(r"\s+", " ", t))
    return t.strip()[:240]


def _clean(store: RepoStore, raw: dict, declared: dict | None, cites: list, dropped: list) -> dict:
    stages, ids = [], set()
    fixed = {s["id"]: s for s in (declared or {}).get("stages", [])}
    given = [s for s in raw.get("stages", []) if isinstance(s, dict)]
    if declared:  # every declared stage, in the model's order where it gave one
        order = {_slug(str(s.get("id", ""))): i for i, s in enumerate(given)}
        by_id = {_slug(str(s.get("id", ""))): s for s in given}
        given = [{**{"id": sid}, **by_id.get(sid, {})} for sid in sorted(fixed, key=lambda k: order.get(k, 99))]
    for s in given[:MAX_STAGES]:
        sid = _slug(str(s.get("id") or s.get("name") or ""))
        if sid in ids:
            continue
        typ = str(s.get("type", "")).lower()
        desc = verify_text(store, str(s.get("description", "")), cites, dropped)
        if sid in fixed and "[" not in desc:  # lost its citation: point at the declaration
            desc = (desc + " " if desc else "") + ref(*fixed[sid]["cite"])
            desc = verify_text(store, desc, cites, dropped)
        m = re.search(r"\[([^\[\]]+):(\d+)-(\d+)\]", desc)
        cite = check_ref(store, m.group(1), m.group(2), m.group(3)) if m else None
        if not cite:
            continue  # a stage must point at real code
        ids.add(sid)
        stages.append({
            "id": sid, "name": str(s.get("name") or fixed.get(sid, {}).get("name") or _name(sid))[:32],
            "type": typ if typ in TYPES else fixed.get(sid, {}).get("type") or _type_guess(sid),
            "description": desc,
            "narration": _spoken(s.get("narration")),
            "cite": {k: cite[k] for k in ("file", "start_line", "end_line")}})
    order = {s["id"]: i for i, s in enumerate(stages)}
    links, seen = [], set()
    raw_links = raw.get("links", [])
    if declared:
        raw_links = [{"from": a, "to": b, "label": lbl} for a, b, lbl in declared["links"]] + \
                    [x for x in raw_links if isinstance(x, dict)]
    for x in raw_links:
        if not isinstance(x, dict):
            continue
        a, b = _slug(str(x.get("from", ""))), _slug(str(x.get("to", "")))
        if a not in order or b not in order or a == b or (a, b) in seen:
            continue
        seen.add((a, b))
        links.append({"from": a, "to": b, "label": str(x.get("label") or "")[:24],
                      "loop": order[b] < order[a]})
    fed = {x["to"] for x in links if not x["loop"]}
    for a, b in zip(stages, stages[1:]):  # a stage nothing feeds runs after the one before it
        if b["id"] not in fed:
            links.append({"from": a["id"], "to": b["id"], "label": "", "loop": False})
    kind = str(raw.get("kind", "")).lower()
    return {"kind": kind if kind in KINDS else (declared or {}).get("kind", "app"),
            "title": str(raw.get("title") or "How it runs")[:60],
            "summary": verify_text(store, str(raw.get("summary", "")), cites, dropped),
            "intro": _spoken(raw.get("intro")),
            "stages": stages, "links": links}


def build_pipeline(store: RepoStore, llm_override: dict | None = None, refresh: bool = False) -> dict:
    override = {k: v for k, v in (llm_override or {}).items() if v is not None}
    cached = store.cache_get("pipeline")
    if cached and not refresh and cached.get("snapshot") == store.snapshot_hash \
            and (cached.get("mode") == "llm" or not llm.can_use(override)):
        return cached
    declared = declared_graph(store)
    sig = signals(store)
    if declared and declared["source"].startswith("GitHub Actions") and _kind(sig) in ("agent", "rag", "ml"):
        declared = None  # CI is not this repo's pipeline: map the agent / model code instead
    kind = declared["kind"] if declared else _kind(sig)
    mode, raw = "offline", None
    if llm.can_use(override):
        try:
            raw = llm.complete_json(SYSTEM_PROMPT, _prompt(store, declared, kind), max_tokens=3000, **override)
            mode = "llm"
        except (LLMError, ValueError) as e:
            log.warning("pipeline: FALLBACK to the declared graph (%s)", e)
    if raw is None and declared:
        raw = _from_declared(store, declared)
    cites: list = []
    dropped: list = []
    out = _clean(store, raw or {}, declared, cites, dropped)
    if declared and len(out["stages"]) < 2:  # the model's answer was unusable: draw what the code declares
        out = _clean(store, _from_declared(store, declared), declared, cites, dropped)
    out.update({
        "found": len(out["stages"]) >= 2,
        "source": declared["source"] if declared else ("Sherpa's reading of the code" if mode == "llm" else None),
        "signals": sig, "citations": cites, "dropped": dropped, "mode": mode,
        "model": (override.get("model") or llm.model) if mode == "llm" else None,
        "snapshot": store.snapshot_hash,
    })
    store.cache_put("pipeline", out)
    return out
