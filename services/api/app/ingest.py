"""Ingest: clone a GitHub URL or walk a local path into chunked snapshot."""
import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import List, Tuple

from .chunk import Chunk, chunk_file
from .config import settings

log = logging.getLogger(__name__)

IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
               "dist", "build", ".next", ".turbo", "coverage", ".pytest_cache"}
IGNORE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff",
              ".woff2", ".ttf", ".eot", ".mp4", ".pdf", ".zip", ".lock",
              # secrets / databases / build junk — never index, never send to an LLM
              ".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx",
              ".keystore", ".jks", ".tsbuildinfo"}
IGNORE_FILES = {".DS_Store", "package-lock.json", "pnpm-lock.yaml",
                "id_rsa", "id_ed25519", ".npmrc", ".pypirc", ".netrc"}
ENV_TEMPLATES = (".example", ".sample", ".template", ".dist")
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
    name = parts[-1]
    if name in IGNORE_FILES:
        return False
    # .env, .env.local, prod.env … (but keep .env.example and friends)
    if (name.startswith(".env") or name.endswith(".env")) and not name.endswith(ENV_TEMPLATES):
        return False
    _, ext = os.path.splitext(path)
    if ext.lower() in IGNORE_EXT:
        return False
    return True


def _is_binary(full: str) -> bool:
    try:
        with open(full, "rb") as f:
            return b"\0" in f.read(8192)
    except OSError:
        return True


def _walk(root: str) -> List[str]:
    out = []
    # never index Sherpa's own snapshot store (chunks.json / sherpa.db)
    data_dir = os.path.realpath(settings.data_dir)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS
                       and os.path.realpath(os.path.join(dirpath, d)) != data_dir]
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
            if _is_binary(full):
                continue
            out.append(full)
            if len(out) >= MAX_FILES:
                log.warning("ingest: hit MAX_FILES=%d under %s; remaining files skipped",
                            MAX_FILES, root)
                return sorted(out)
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


def repo_name(source: str) -> str:
    m = re.search(r"([^/:]+/[^/]+?)(?:\.git)?/?$", source.strip())
    return m.group(1) if m else os.path.basename(source.rstrip("/"))


def snapshot_dir(root: str, prefix: str = "") -> Tuple[List[Chunk], dict, dict]:
    """Walk + chunk a directory. Returns (chunks, roles, sources)."""
    chunks: List[Chunk] = []
    roles: dict = {}
    sources: dict = {}
    for full in _walk(root):
        rel = prefix + os.path.relpath(full, root).replace(os.sep, "/")
        try:
            with open(full, encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError as e:
            log.warning("ingest: skipped unreadable %s: %s", rel, e)
            continue
        if not text.strip():
            continue
        sources[rel] = text
        roles[rel] = detect_role(rel, text)
        chunks.extend(chunk_file(text, rel, settings.chunk_lines, settings.chunk_overlap))
    return chunks, roles, sources


def ingest_source(repo_url: str | None, local_path: str | None,
                  branch: str = "main") -> Tuple[str, List[Chunk], dict, dict]:
    """Returns (repo_id, chunks, meta, sources)."""
    cleanup = None
    commit = ""
    if repo_url:
        try:
            root = _clone(repo_url, branch)
        except subprocess.CalledProcessError as e:
            if not branch:
                raise
            # many repos use master/trunk — retry on the default branch, and say so
            log.warning("ingest: branch %r not found for %s (%s); cloning default branch",
                        branch, repo_url, (e.stderr or "").strip()[:160])
            root = _clone(repo_url, "")
            branch = ""
        cleanup = os.path.dirname(root)
        source = repo_url
        try:
            commit = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"],
                                    capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:  # noqa: BLE001
            commit = ""
    elif local_path:
        root = os.path.abspath(os.path.expanduser(local_path))
        if not os.path.isdir(root):
            raise ValueError(f"local_path not found: {root}")
        source = root
    else:
        raise ValueError("provide repo_url or local_path")

    repo_id = repo_id_for(source)
    try:
        chunks, file_roles, sources = snapshot_dir(root)
    finally:
        if cleanup and os.path.isdir(cleanup):
            shutil.rmtree(cleanup, ignore_errors=True)
    if not chunks:
        raise ValueError("no readable source files found in the repository")

    name = repo_name(source) if repo_url else os.path.basename(root.rstrip("/"))
    meta = {"source": source, "name": name, "branch": branch,
            "commit": commit, "kind": "git" if repo_url else "local",
            "indexed_at": time.time(), "roles": file_roles,
            "languages": _langs(file_roles)}
    return repo_id, chunks, meta, sources


def _langs(roles: dict) -> List[str]:
    exts = {}
    for p in roles:
        _, ext = os.path.splitext(p)
        exts[ext or "?"] = exts.get(ext or "?", 0) + 1
    return sorted(exts, key=lambda e: -exts[e])[:8]
