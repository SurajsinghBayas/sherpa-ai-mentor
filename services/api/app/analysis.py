"""Static analysis over a snapshot — deterministic facts the LLM narrates.

- import graph (Python + JS/TS, resolved to files in the snapshot, with line numbers)
- components: directory groups split until the repo has a readable number of parts
- entrypoints, top-level symbols, and starter-task signals (TODO/FIXME, untested
  modules, long functions, missing docstrings)

Everything here cites real `file:line` so agents can ground their prose on it.
"""
import ast
import os
import posixpath
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .store import RepoStore

CODE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs",
            ".java", ".kt", ".rb", ".php", ".cs", ".swift", ".vue", ".svelte"}
JS_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte")
SKIP_COMPONENT_DIRS = {"test", "tests", "__tests__", "spec", "specs", "docs", "doc",
                       "examples", "example", ".github", "scripts", "fixtures"}

PY_IMPORT = re.compile(r"^\s*(?:from\s+(\.*[\w.]*)\s+import\s+([\w*, ()]+)|import\s+([\w., ]+))", re.M)
JS_IMPORT = re.compile(
    r"""(?:import\s+(?:[\w*{}\s,]+\s+from\s+)?|export\s+[\w*{}\s,]+\s+from\s+|require\(\s*|import\(\s*)['"]([^'"]+)['"]""")
TODO_RE = re.compile(r"(?:#|//|/\*|\*|<!--)\s*(TODO|FIXME|HACK|XXX)\b[:\s-]*(.*)", re.I)
ENTRY_NAMES = {"main.py", "app.py", "server.py", "manage.py", "wsgi.py", "asgi.py",
               "__main__.py", "index.ts", "index.js", "main.ts", "main.js", "server.ts",
               "server.js", "app.ts", "app.js", "main.go", "main.rs", "page.tsx",
               "layout.tsx", "_app.tsx", "App.tsx", "App.jsx"}
ENTRY_SIGNALS = re.compile(
    r"__name__\s*==\s*['\"]__main__['\"]|FastAPI\(|Flask\(|express\(\)|createServer\(|"
    r"\.listen\(|ReactDOM\.createRoot|createApp\(|func main\(\)|fn main\(\)|"
    r"public static void main|NestFactory\.create|uvicorn\.run")


def is_code(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in CODE_EXT


@dataclass
class Edge:
    src: str
    dst: str
    line: int


@dataclass
class Analysis:
    files: list[str]
    edges: list[Edge]
    components: dict[str, list[str]]           # component key -> files
    entrypoints: list[tuple[str, int, str]]    # (file, line, why)
    symbols: dict[str, list[tuple[str, int, int, str]]] = field(default_factory=dict)

    def component_of(self, path: str) -> str | None:
        for key, files in self.components.items():
            if path in files:
                return key
        return None

    def component_edges(self) -> list[tuple[str, str, int, Edge]]:
        """(from, to, count, example edge) between components."""
        agg: dict[tuple[str, str], list[Edge]] = defaultdict(list)
        for e in self.edges:
            a, b = self.component_of(e.src), self.component_of(e.dst)
            if a and b and a != b:
                agg[(a, b)].append(e)
        return sorted(((a, b, len(es), es[0]) for (a, b), es in agg.items()),
                      key=lambda t: -t[2])

    def in_degree(self) -> Counter:
        return Counter(e.dst for e in self.edges)


# ---------- import resolution ----------

def _py_module_index(files: list[str]) -> dict[str, str]:
    """dotted module -> file, for every suffix of the path (handles src/ layouts)."""
    idx: dict[str, str] = {}
    for f in files:
        if not f.endswith(".py"):
            continue
        parts = f[:-3].split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        for i in range(len(parts)):
            key = ".".join(parts[i:])
            if key and (key not in idx or len(f) < len(idx[key])):
                idx[key] = f
    return idx


def _resolve_py(src: str, mod: str, names: str, idx: dict[str, str], files: set) -> list[str]:
    out = []
    if mod.startswith("."):
        level = len(mod) - len(mod.lstrip("."))
        base = src.split("/")[:-1]
        base = base[:len(base) - (level - 1)] if level > 1 else base
        rest = mod.lstrip(".")
        cands = []
        prefix = "/".join(base + (rest.split(".") if rest else []))
        cands.append(prefix)
        for n in re.split(r"[,\s()]+", names or ""):
            if n and n != "*":
                cands.append(prefix + "/" + n)
        for c in cands:
            for f in (c + ".py", c + "/__init__.py"):
                if f in files:
                    out.append(f)
        return out
    parts = mod.split(".")
    for n in range(len(parts), 0, -1):
        f = idx.get(".".join(parts[:n]))
        if f:
            out.append(f)
            break
    return out


def _resolve_js(src: str, spec: str, files: set) -> str | None:
    if spec.startswith("."):
        base = posixpath.normpath(posixpath.join(posixpath.dirname(src), spec))
        cands = [base]
    elif spec.startswith(("@/", "~/")):
        rest = spec[2:]
        cands = [rest, "src/" + rest]
        # monorepos: resolve against the importing app's root too
        parts = src.split("/")
        for i in range(1, len(parts)):
            cands.append("/".join(parts[:i]) + "/" + rest)
    else:
        return None
    for c in cands:
        for ext in ("", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".vue", "/index.ts",
                    "/index.tsx", "/index.js", "/index.jsx"):
            if c + ext in files:
                return c + ext
    return None


def import_edges(store: RepoStore, files: list[str]) -> list[Edge]:
    fileset = set(files)
    idx = _py_module_index(files)
    edges: list[Edge] = []
    seen = set()
    for f in files:
        text = "\n".join(store.lines(f))
        if f.endswith(".py"):
            for m in PY_IMPORT.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                if m.group(1) is not None:
                    targets = _resolve_py(f, m.group(1), m.group(2), idx, fileset)
                else:
                    targets = []
                    for mod in m.group(3).split(","):
                        targets += _resolve_py(f, mod.strip().split(" ")[0], "", idx, fileset)
                for t in targets:
                    if t != f and (f, t) not in seen:
                        seen.add((f, t))
                        edges.append(Edge(f, t, line))
        elif f.endswith(JS_EXT):
            for m in JS_IMPORT.finditer(text):
                t = _resolve_js(f, m.group(1), fileset)
                if t and t != f and (f, t) not in seen:
                    seen.add((f, t))
                    edges.append(Edge(f, t, text.count("\n", 0, m.start()) + 1))
    return edges


# ---------- components ----------

def _group(files: list[str], depth_of: dict[str, int]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for f in files:
        parts = f.split("/")
        d = min(depth_of.get(f, 1), len(parts) - 1)
        groups["/".join(parts[:d]) if d > 0 else "(root)"].append(f)
    return groups


def build_components(files: list[str], target: int = 10) -> dict[str, list[str]]:
    """Split directory groups breadth-first until there are ~`target` components.

    Shallow groups split before deep ones, so a repo reads as
    backend/api, backend/core, frontend/routes … rather than 30 UI folders.
    """
    all_code = [f for f in files if is_code(f)]
    code = [f for f in all_code
            if not any(p.lower() in SKIP_COMPONENT_DIRS for p in f.split("/")[:-1])]
    if len(code) < 0.4 * len(all_code):  # e.g. a spec/test-heavy repo: keep everything
        code = all_code
    if not code:
        code = files
    depth = {f: 1 for f in code}
    groups = _group(code, depth)
    big = max(6, int(0.15 * len(code)))
    for _ in range(40):
        best = None
        for key, members in groups.items():
            deeper = [f for f in members if len(f.split("/")) - 1 > depth[f]]
            if key == "(root)" or len(deeper) < 2:
                continue
            kids = {"/".join(f.split("/")[:depth[f] + 1]) for f in deeper}
            if len(groups) >= target and (len(members) <= big or len(kids) > 5):
                continue  # enough parts; only split oversized groups into a few parts
            rank = (key.count("/"), -len(members))
            if best is None or rank < best[0]:
                best = (rank, key, deeper, kids)
        if best is None:
            break
        _, key, deeper, kids = best
        for f in deeper:
            depth[f] += 1
        new = _group(code, depth)
        if len(kids) > 1 and len(new) > target + 6:
            for f in deeper:  # this split would explode the map; stop here
                depth[f] -= 1
            break
        groups = new
    # fold single-file groups into an existing parent (e.g. app/login/page.tsx)
    for key in sorted(groups, key=lambda k: -k.count("/")):
        parent = key.rsplit("/", 1)[0] if "/" in key else None
        if parent in groups and len(groups[key]) == 1 and key != parent:
            groups[parent].extend(groups.pop(key))
    # merge tiny groups into their parent so the map stays readable
    while len(groups) > target + 4:
        key, members = min(groups.items(), key=lambda kv: len(kv[1]))
        parent = key.rsplit("/", 1)[0] if "/" in key else "(root)"
        groups.setdefault(parent, []).extend(members)
        del groups[key]
    return {k: sorted(v) for k, v in sorted(groups.items())}


# ---------- entrypoints & symbols ----------

def find_entrypoints(store: RepoStore, files: list[str]) -> list[tuple[str, int, str]]:
    out = []
    for f in files:
        if not is_code(f):
            continue
        name = f.split("/")[-1]
        ls = store.lines(f)
        for i, ln in enumerate(ls[:400], 1):
            m = ENTRY_SIGNALS.search(ln)
            if m:
                out.append((f, i, m.group(0).strip()))
                break
        else:
            if name in ENTRY_NAMES and len(f.split("/")) <= 4:
                out.append((f, 1, f"conventional entry file ({name})"))
    out.sort(key=lambda t: (len(t[0].split("/")), t[0]))
    return out[:12]


JS_SYMBOL = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\s+(\w+)|class\s+(\w+)|"
    r"(?:const|let)\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>)")


def symbols_of(store: RepoStore, f: str) -> list[tuple[str, int, int, str]]:
    """(name, start, end, kind) for top-level defs."""
    ls = store.lines(f)
    out = []
    if f.endswith(".py"):
        try:
            tree = ast.parse("\n".join(ls))
        except (SyntaxError, ValueError):
            return out
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = "class" if isinstance(n, ast.ClassDef) else "function"
                out.append((n.name, n.lineno, getattr(n, "end_lineno", n.lineno) or n.lineno, kind))
    elif f.endswith(JS_EXT):
        for i, ln in enumerate(ls, 1):
            m = JS_SYMBOL.match(ln)
            if m:
                name = next(g for g in m.groups() if g)
                out.append((name, i, i, "class" if m.group(2) else "function"))
    return out


def analyze(store: RepoStore) -> Analysis:
    files = store.files()
    real = [f for f in files if not f.startswith("web/")]
    a = Analysis(files=real, edges=import_edges(store, real),
                 components=build_components(real),
                 entrypoints=find_entrypoints(store, real))
    return a


# ---------- starter-task signals ----------

def task_signals(store: RepoStore, a: Analysis, limit: int = 40) -> list[dict]:
    """Concrete, citable opportunities for a first contribution."""
    sigs: list[dict] = []
    files = a.files
    test_text = " ".join(f.lower() for f in files if re.search(r"(^|/)(tests?|__tests__|spec)/|test_|_test\.|\.test\.|\.spec\.", f))
    for f in files:
        if not is_code(f):
            continue
        ls = store.lines(f)
        for i, ln in enumerate(ls, 1):
            m = TODO_RE.search(ln)
            if m and len(m.group(2).strip()) > 3:
                sigs.append({"kind": "todo", "file": f, "start_line": i, "end_line": min(i + 6, len(ls)),
                             "detail": f"{m.group(1).upper()}: {m.group(2).strip()[:160]}"})
        is_test = bool(re.search(r"(^|/)(tests?|__tests__|spec)/|test_|_test\.|\.test\.|\.spec\.", f))
        if is_test:
            continue
        stem = os.path.splitext(f.split("/")[-1])[0].lower()
        syms = symbols_of(store, f)
        if syms and stem not in ("__init__", "index", "main", "conftest", "setup") and stem not in test_text:
            s0 = syms[0]
            sigs.append({"kind": "untested", "file": f, "start_line": s0[1],
                         "end_line": min(s0[2], s0[1] + 30),
                         "detail": f"No test file mentions `{stem}`; it defines {len(syms)} top-level symbol(s) e.g. `{s0[0]}`"})
        for name, s, e, kind in syms:
            if e - s > 70:
                sigs.append({"kind": "long_function", "file": f, "start_line": s, "end_line": e,
                             "detail": f"`{name}` is {e - s + 1} lines long — candidate for a small extract-function refactor"})
            if f.endswith(".py") and kind == "function" and not name.startswith("_"):
                body = ls[s:s + 2]
                if body and not any('"""' in b or "'''" in b for b in body):
                    sigs.append({"kind": "missing_docstring", "file": f, "start_line": s,
                                 "end_line": min(e, s + 15),
                                 "detail": f"public function `{name}` has no docstring"})
    order = {"todo": 0, "untested": 1, "missing_docstring": 2, "long_function": 3}
    sigs.sort(key=lambda d: (order[d["kind"]], d["file"]))
    # diversify: cap per kind so one category doesn't crowd out the rest
    caps = {"todo": 12, "untested": 12, "long_function": 6, "missing_docstring": 4}
    out, per = [], Counter()
    for s in sigs:
        if per[s["kind"]] < caps[s["kind"]]:
            out.append(s)
            per[s["kind"]] += 1
    return out[:limit]
