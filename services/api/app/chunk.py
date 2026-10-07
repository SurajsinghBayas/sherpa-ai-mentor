"""AST-aware chunking with safe fallbacks.

Goal: keep provenance (file:start-end) on every chunk so answers can cite.
- Python: split on top-level def/class via `ast`.
- Others: split on blank-line-separated blocks capped at chunk_lines.
- Overlap: carry trailing lines forward for context.
"""
import ast
from dataclasses import dataclass
from typing import List


@dataclass
class Chunk:
    file: str
    start_line: int
    end_line: int
    text: str
    kind: str = "code"


def chunk_python(source: str, path: str, max_lines: int = 60, overlap: int = 12) -> List[Chunk]:
    lines = source.splitlines()
    if not lines:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return chunk_generic(source, path, max_lines, overlap)
    bounds = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            s = node.lineno
            e = getattr(node, "end_lineno", s + max_lines - 1) or s
            bounds.append((s, min(e, len(lines))))
    if not bounds:
        return chunk_generic(source, path, max_lines, overlap)
    chunks: List[Chunk] = []
    # module header (imports/docstring) as its own chunk
    first = bounds[0][0]
    if first > 1:
        chunks.append(Chunk(path, 1, min(first - 1, max_lines),
                            "\n".join(lines[: min(first - 1, max_lines)]), "header"))
    for (s, e) in bounds:
        if e - s + 1 > max_lines:
            chunks.extend(chunk_generic("\n".join(lines[s - 1: e]), path,
                                        max_lines, overlap, offset=s - 1))
        else:
            chunks.append(Chunk(path, s, e, "\n".join(lines[s - 1: e]), "def"))
    return chunks


def chunk_generic(source: str, path: str, max_lines: int = 60,
                  overlap: int = 12, offset: int = 0) -> List[Chunk]:
    lines = source.splitlines()
    chunks: List[Chunk] = []
    i = 0
    n = len(lines)
    while i < n:
        j = min(i + max_lines, n)
        # prefer breaking on blank line near the end
        if j < n:
            for k in range(j, max(j - 10, i), -1):
                if lines[k - 1].strip() == "":
                    j = k
                    break
        chunks.append(Chunk(path, offset + i + 1, offset + j,
                            "\n".join(lines[i:j]), "code"))
        if j >= n:
            break
        i = max(j - overlap, i + 1)
    return chunks


def chunk_file(source: str, path: str, max_lines: int = 60, overlap: int = 12) -> List[Chunk]:
    if path.endswith(".py"):
        return chunk_python(source, path, max_lines, overlap)
    if path.endswith((".md", ".mdx")):
        # docs: chunk per heading block
        lines = source.splitlines()
        chunks: List[Chunk] = []
        cur_start = 1
        cur: List[str] = []
        for idx, ln in enumerate(lines, start=1):
            if ln.startswith("#") and cur:
                chunks.append(Chunk(path, cur_start, idx - 1, "\n".join(cur), "docs"))
                cur_start = idx
                cur = []
            cur.append(ln)
            if len(cur) >= max_lines:
                chunks.append(Chunk(path, cur_start, idx, "\n".join(cur), "docs"))
                cur_start = idx + 1
                cur = []
        if cur:
            chunks.append(Chunk(path, cur_start, len(lines), "\n".join(cur), "docs"))
        return chunks or [Chunk(path, 1, max(1, len(lines)), source, "docs")]
    return chunk_generic(source, path, max_lines, overlap)
