"""Ingest: clone a GitHub URL or walk a local path into chunked snapshot."""
import base64
import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import List, Tuple
from urllib.parse import urlparse

from .chunk import Chunk, chunk_file
from .config import settings

log = logging.getLogger(__name__)

IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
               "dist", "build", ".next", ".turbo", "coverage", ".pytest_cache",
               # more generated / vendored / editor output (uploads often include these)
               "vendor", "bower_components", "target", ".gradle", ".idea", ".mypy_cache",
               ".ruff_cache", ".tox", ".nuxt", ".svelte-kit", ".parcel-cache", ".terraform",
               "__MACOSX", ".hg", ".svn"}
IGNORE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff",
              ".woff2", ".ttf", ".eot", ".mp4", ".pdf", ".zip", ".lock",
              # secrets / databases / build junk — never index, never send to an LLM
              ".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx",
              ".keystore", ".jks", ".tsbuildinfo",
              # compiled artifacts, archives, media and model weights
              ".class", ".jar", ".war", ".o", ".so", ".dll", ".exe", ".dylib", ".a", ".wasm",
              ".pyc", ".map", ".bin", ".dat", ".mp3", ".wav", ".webp", ".avif", ".bmp", ".tiff",
              ".psd", ".gz", ".tar", ".tgz", ".7z", ".rar", ".bz2", ".xz", ".iso", ".dmg",
              ".pkl", ".pt", ".onnx", ".h5", ".parquet", ".npy"}
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


def skip_reason(path: str) -> str | None:
    """Why a path is left out of the index (None = keep it). `path` uses os.sep."""
    parts = path.split(os.sep)
    if any(p in IGNORE_DIRS for p in parts[:-1]):
        return "generated"  # node_modules, .git, build output, vendored code …
    name = parts[-1]
    if name in IGNORE_FILES or name.startswith("._"):  # ._x: macOS resource forks in zips
        return "secret" if name in ("id_rsa", "id_ed25519", ".npmrc", ".pypirc", ".netrc") else "generated"
    # .env, .env.local, prod.env … (but keep .env.example and friends)
    if (name.startswith(".env") or name.endswith(".env")) and not name.endswith(ENV_TEMPLATES):
        return "secret"
    if name.endswith((".min.js", ".min.css")):  # minified bundles: generated, unreadable
        return "generated"
    _, ext = os.path.splitext(path)
    if ext.lower() in IGNORE_EXT:
        return "secret" if ext.lower() in (".pem", ".key", ".p12", ".pfx", ".keystore", ".jks") else "binary"
    return None


def _should_keep(path: str) -> bool:
    return skip_reason(path) is None


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
    real_root = os.path.realpath(root)
    for dirpath, dirnames, filenames in os.walk(root):  # does not descend into symlinked dirs
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS
                       and os.path.realpath(os.path.join(dirpath, d)) != data_dir]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            if not _should_keep(rel):
                continue
            # a repo can ship `x -> /proc/self/environ` or `../../etc/passwd`: never read
            # through a symlink, and never outside the checkout
            if os.path.islink(full) or not os.path.realpath(full).startswith(real_root + os.sep):
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


class IngestError(ValueError):
    """A clone/index failure whose message is safe to show the user."""


# Git must never prompt, run user hooks, follow non-https transports, or pull LFS blobs.
_GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "/bin/true", "SSH_ASKPASS": "/bin/true",
            "GIT_LFS_SKIP_SMUDGE": "1", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
_GIT_SAFE = ["-c", "protocol.allow=never", "-c", "protocol.https.allow=always",
             "-c", "core.hooksPath=" + os.devnull, "-c", "credential.helper=",
             "-c", "http.followRedirects=initial"]


def _dir_bytes(root: str) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            try:
                total += os.lstat(os.path.join(dirpath, fn)).st_size
            except OSError:
                pass
    return total


def _git_error(stderr: str, with_token: bool = False) -> str:
    s = (stderr or "").lower()
    if "remote branch" in s and "not found" in s:
        return "branch not found"
    # GitHub answers a token without Contents access with 403 "Write access … not granted"
    if "error: 403" in s or "not granted" in s or "permission" in s:
        if with_token:
            return ("the access token can't read this repository: give it read-only Contents "
                    "access to this repo (for an org repo, the org may need to approve it)")
        return "access denied: the repository is private; turn on Private mode and add a token"
    if "not found" in s or "could not read username" in s or "authentication" in s:
        if with_token:
            return "the access token was rejected, or it can't read this repository"
        return ("repository not found, or it is private: turn on Private mode and add a "
                "read-only access token")
    if "could not resolve host" in s or "unable to access" in s:
        return "couldn't reach the git host; try again shortly"
    return "git clone failed"


# username each host expects alongside an access token in HTTP basic auth
_TOKEN_USER = {"github.com": "x-access-token", "gitlab.com": "oauth2", "bitbucket.org": "x-token-auth"}


def _token_env(url: str, token: str) -> dict:
    """Git config (via environment, so it's not on the command line, in the URL, or written to
    .git/config) that sends the token as an auth header. Redirects are refused so the header
    can't follow the clone to another host."""
    if not token:
        return {}
    host = (urlparse(url).hostname or "").lower()
    user = next((u for h, u in _TOKEN_USER.items() if host == h or host.endswith("." + h)),
                "x-access-token")
    basic = base64.b64encode(f"{user}:{token}".encode()).decode()
    return {"GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "http.extraHeader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}",
            "GIT_CONFIG_KEY_1": "http.followRedirects", "GIT_CONFIG_VALUE_1": "false"}


def _clone(url: str, branch: str, token: str = "") -> str:
    """Shallow, hardened clone into a fresh temp dir. The dir is removed on any failure."""
    tmp = tempfile.mkdtemp(prefix="sherpa-")
    dest = os.path.join(tmp, "repo")
    cmd = ["git", *_GIT_SAFE, "clone", "--depth", "1", "--single-branch", "--no-tags",
           "--no-recurse-submodules"]
    if branch:
        cmd += ["--branch", branch]
    cmd += ["--", url, dest]
    try:
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True,
                           timeout=settings.clone_timeout_seconds,
                           env={**os.environ, **_GIT_ENV, **_token_env(url, token)})
        except subprocess.TimeoutExpired:
            raise IngestError(f"clone took longer than {settings.clone_timeout_seconds}s; "
                              "the repository is too large")
        size = _dir_bytes(dest)
        if size > settings.max_repo_mb * 1024 * 1024:
            raise IngestError(f"repository is {size // (1024 * 1024)} MB; the limit is "
                              f"{settings.max_repo_mb} MB")
        return dest
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


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


def read_dir(root: str, prefix: str = "") -> Tuple[dict, dict]:
    """Walk a directory and read every indexable file. Returns (sources, roles)."""
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
    return sources, roles


def chunk_sources(sources: dict, only=None) -> List[Chunk]:
    """Chunk every file, or just the paths in `only` (incremental re-index)."""
    chunks: List[Chunk] = []
    for rel, text in sources.items():
        if only is None or rel in only:
            chunks.extend(chunk_file(text, rel, settings.chunk_lines, settings.chunk_overlap))
    return chunks


def snapshot_dir(root: str, prefix: str = "") -> Tuple[List[Chunk], dict, dict]:
    """Walk + chunk a directory. Returns (chunks, roles, sources)."""
    sources, roles = read_dir(root, prefix)
    return chunk_sources(sources), roles, sources


def remote_head(repo_url: str, branch: str = "") -> str:
    """Latest commit sha of a branch (default branch when blank) without cloning.

    One small `git ls-remote` round trip, so checking for new commits is cheap.
    """
    ref = f"refs/heads/{branch}" if branch else "HEAD"
    cmd = ["git", *_GIT_SAFE, "ls-remote", "--", repo_url, ref]
    try:
        out = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30,
                             env={**os.environ, **_GIT_ENV}).stdout
    except subprocess.TimeoutExpired:
        raise IngestError("the git host didn't answer in time; try again shortly")
    except subprocess.CalledProcessError as e:
        raise IngestError(_git_error(e.stderr)) from e
    sha = out.split()[0] if out.strip() else ""
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise IngestError("branch not found" if branch else "couldn't read the repository's latest commit")
    return sha


def fetch_source(repo_url: str | None, local_path: str | None,
                 branch: str = "", token: str = "") -> Tuple[dict, dict]:
    """Clone (or open) a source and read its files without chunking. Returns (sources, meta).

    `token` (private repos) is only used for this clone and is never stored."""
    cleanup = None
    commit = ""
    if repo_url:
        try:
            root = _clone(repo_url, branch, token)
        except subprocess.CalledProcessError as e:
            if not branch or "not found" not in (e.stderr or "").lower():
                raise IngestError(_git_error(e.stderr, bool(token))) from e
            # many repos use master/trunk — retry on the default branch, and say so
            log.warning("ingest: branch %r not found for %s (%s); cloning default branch",
                        branch, repo_url, (e.stderr or "").strip()[:160])
            try:
                root = _clone(repo_url, "", token)
            except subprocess.CalledProcessError as e2:
                raise IngestError(_git_error(e2.stderr, bool(token))) from e2
            branch = ""
        cleanup = os.path.dirname(root)
        source = repo_url
        try:  # full sha: compared with `git ls-remote` to detect new commits
            commit = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
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

    try:
        sources, file_roles = read_dir(root)
    finally:
        if cleanup and os.path.isdir(cleanup):
            shutil.rmtree(cleanup, ignore_errors=True)
    if not sources:
        raise IngestError("no readable source files found in the repository")

    name = repo_name(source) if repo_url else os.path.basename(root.rstrip("/"))
    meta = {"source": source, "name": name, "branch": branch,
            "commit": commit, "kind": "git" if repo_url else "local",
            "indexed_at": time.time(), "roles": file_roles,
            "languages": _langs(file_roles)}
    return sources, meta


def ingest_source(repo_url: str | None, local_path: str | None, branch: str = "main",
                  token: str = "") -> Tuple[str, List[Chunk], dict, dict]:
    """Returns (repo_id, chunks, meta, sources)."""
    sources, meta = fetch_source(repo_url, local_path, branch, token)
    chunks = chunk_sources(sources)
    if not chunks:
        raise IngestError("no readable source files found in the repository")
    return repo_id_for(meta["source"]), chunks, meta, sources


def _langs(roles: dict) -> List[str]:
    exts = {}
    for p in roles:
        _, ext = os.path.splitext(p)
        exts[ext or "?"] = exts.get(ext or "?", 0) + 1
    return sorted(exts, key=lambda e: -exts[e])[:8]
