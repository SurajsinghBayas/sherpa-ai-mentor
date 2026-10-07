"""Ingest: clone a GitHub URL or walk a local path into chunked snapshot."""
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from typing import List, Tuple

from .chunk import Chunk, chunk_file
from .config import settings

IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
               "dist", "build", ".next", ".turbo", "coverage", ".pytest_cache"}
IGNORE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff",
              ".woff2", ".ttf", ".eot", ".mp4", ".pdf", ".zip", ".lock"}
MAX_FILE_BYTES = 400_000
MAX_FILES = 1500

LANG_BY_EXT = {".py": "python", ".ts": "ts", ".tsx": "ts", ".js": "js",
               ".jsx": "js", ".go": "go", ".rs": "rust", ".java": "java",
               ".md": "docs", ".mdx": "docs"}


def repo_id_for(source: str) -> str:
    return hashlib.sha1(source.encode()).hexdigest()[:12]


def _should_keep(path: str) -> bool:
    parts = path.split(os.sep)
    if any(p in IGNORE_DIRS for p in parts):
        return False
    _, ext = os.path.splitext(path)
    if ext.lower() in IGNORE_EXT:
        return False
    return True


def _walk(root: str) -> List[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            if not _should_keep(rel):
                continue
            try:
                if os.path.getsize(full) > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            out.append(full)
            if len(out) >= MAX_FILES:
                return out
    return sorted(out)


def _clone(url: str, branch: str) -> str:
    tmp = tempfile.mkdtemp(prefix="sherpa-")
    dest = os.path.join(tmp, "repo")
    cmd = ["git", "clone", "--depth", "1"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [url, dest]
    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180)
    return dest


IMPORT_RE = re.compile(r"^\s*(?:import|from|require\(|export .* from)", re.M)


def detect_role(path: str, text: str) -> str:
    p = path.lower()
    head = text[:2000].lower()
    if any(k in p for k in ("route", "router", "endpoint", "controller", "view", "handler")):
        return "route/handler"
    if any(k in p for k in ("model", "schema", "entity", "migration")):
        return "data model"
    if any(k in p for k in ("auth", "login", "signup", "session", "jwt")):
        return "auth"
    if any(k in p for k in ("test", "spec", "__test__")):
        return "test"
    if "def " in head and ("fastapi" in head or "flask" in head or "route" in head):
        return "route/handler"
    if p.endswith((".md", ".mdx")):
        return "docs"
    return "module"


def ingest_source(repo_url: str | None, local_path: str | None,
                  branch: str = "main") -> Tuple[str, List[Chunk], dict]:
    """Returns (repo_id, chunks, meta)."""
    cleanup = None
    if repo_url:
        root = _clone(repo_url, branch)
        cleanup = os.path.dirname(root)
        source = repo_url
    elif local_path:
        root = os.path.abspath(os.path.expanduser(local_path))
        if not os.path.isdir(root):
            raise ValueError(f"local_path not found: {root}")
        source = root
    else:
        raise ValueError("provide repo_url or local_path")

    repo_id = repo_id_for(source)
    chunks: List[Chunk] = []
    file_roles: dict = {}
    try:
        for full in _walk(root):
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                with open(full, encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except OSError:
                continue
            if not text.strip():
                continue
            file_roles[rel] = detect_role(rel, text)
            for ch in chunk_file(text, rel, settings.chunk_lines, settings.chunk_overlap):
                chunks.append(ch)
    finally:
        if cleanup and os.path.isdir(cleanup):
            shutil.rmtree(cleanup, ignore_errors=True)

    meta = {"source": source, "branch": branch, "roles": file_roles,
            "languages": _langs(file_roles)}
    return repo_id, chunks, meta


def _langs(roles: dict) -> List[str]:
    exts = {}
    for p in roles:
        _, ext = os.path.splitext(p)
        exts[ext or "?"] = exts.get(ext or "?", 0) + 1
    return sorted(exts, key=lambda e: -exts[e])[:8]
