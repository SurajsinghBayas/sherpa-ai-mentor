"""Uploaded codebases: ZIP files, folders (zipped in the browser) and the CLI.

Everything arrives as one ZIP. It is read in memory, never extracted to disk, so a
hostile archive can't write outside a temp dir; entries that are absolute, climb with
`..`, are symlinks or encrypted are skipped, and every read is size-capped so a zip
bomb can't exhaust memory. The accepted files become a manifest the user reviews, then
a background job (review → queued → processing → ready | failed) indexes them with the
same chunk/embed/store pipeline as a git clone.
"""
import gzip
import io
import json
import logging
import os
import re
import stat
import threading
import time
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Tuple

from . import db as dbmod
from .config import settings
from .dbmodels import IngestJob
from .ingest import (MAX_FILE_BYTES, MAX_FILES, IngestError, chunk_sources, detect_role,
                     repo_id_for, skip_reason, _langs)
from .persist import SqlBackend
from .store import RepoStore, file_hash

log = logging.getLogger(__name__)

MAX_ZIP_ENTRIES = 100_000
STALE_AFTER = 15 * 60  # a processing job with no heartbeat for this long has died

LANGUAGE = {".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
            ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".go": "Go",
            ".rs": "Rust", ".java": "Java", ".kt": "Kotlin", ".scala": "Scala", ".rb": "Ruby",
            ".php": "PHP", ".cs": "C#", ".cpp": "C++", ".cc": "C++", ".c": "C", ".h": "C/C++",
            ".hpp": "C++", ".swift": "Swift", ".m": "Objective-C", ".dart": "Dart",
            ".vue": "Vue", ".svelte": "Svelte", ".sql": "SQL", ".sh": "Shell", ".md": "Markdown",
            ".mdx": "Markdown", ".html": "HTML", ".css": "CSS", ".scss": "CSS", ".json": "JSON",
            ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML", ".tf": "Terraform",
            ".proto": "Protobuf", ".graphql": "GraphQL"}

# marker file → project type (checked anywhere in the tree, shallowest first)
PROJECT_MARKERS = [("package.json", "Node.js"), ("tsconfig.json", "TypeScript"),
                   ("next.config.js", "Next.js"), ("next.config.mjs", "Next.js"),
                   ("next.config.ts", "Next.js"), ("vite.config.ts", "Vite"),
                   ("vite.config.js", "Vite"), ("angular.json", "Angular"),
                   ("requirements.txt", "Python"), ("pyproject.toml", "Python"),
                   ("setup.py", "Python"), ("Pipfile", "Python"), ("manage.py", "Django"),
                   ("pom.xml", "Java (Maven)"), ("build.gradle", "Java/Kotlin (Gradle)"),
                   ("build.gradle.kts", "Kotlin (Gradle)"), ("go.mod", "Go"),
                   ("Cargo.toml", "Rust"), ("Gemfile", "Ruby"), ("composer.json", "PHP"),
                   ("pubspec.yaml", "Flutter/Dart"), ("Dockerfile", "Docker"),
                   ("docker-compose.yml", "Docker Compose"), ("compose.yaml", "Docker Compose")]
ENTRY_POINTS = re.compile(
    r"(^|/)(main\.py|app\.py|manage\.py|wsgi\.py|asgi\.py|__main__\.py|server\.(js|ts)|"
    r"index\.(js|ts|tsx|jsx)|main\.(js|ts|tsx|go|rs|java|kt|dart)|app\.(js|ts|tsx)|"
    r"Program\.cs|Application\.java|page\.tsx|layout\.tsx)$")
# app objects and program mains, per language, at the start of a line (so a file that merely
# mentions "FastAPI(" in a string or a regex doesn't count)
ENTRY_CODE = {
    ".py": re.compile(r"^\w+\s*=\s*(FastAPI|Flask)\(|^if __name__ == ['\"]__main__['\"]", re.M),
    ".js": re.compile(r"^\s*(const|let|var)\s+\w+\s*=\s*express\(\)|^\s*\w+\.listen\(", re.M),
    ".ts": re.compile(r"^\s*(const|let|var)\s+\w+\s*=\s*express\(\)|^\s*\w+\.listen\(", re.M),
    ".go": re.compile(r"^func main\(\)", re.M),
    ".rs": re.compile(r"^fn main\(\)", re.M),
    ".java": re.compile(r"^\s*public static void main\(", re.M),
}
TEST_FILE = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test_|_test\.|\.test\.|\.spec\.")


# ── reading an archive ────────────────────────────────────────────────────────
def _safe_rel(name: str) -> str | None:
    """Normalised relative path, or None for anything that could escape the project."""
    n = name.replace("\\", "/")
    if n.startswith("/") or re.match(r"^[A-Za-z]:", n) or "\x00" in n:
        return None
    parts = [p for p in n.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None
    return "/".join(parts)


def _common_root(names) -> str:
    """'repo-main/' when every entry sits under one top folder (GitHub-style zips)."""
    tops = {n.split("/", 1)[0] for n in names}
    if len(tops) == 1 and all("/" in n for n in names):
        return next(iter(tops)) + "/"
    return ""


def read_zip(data: bytes, name: str = "") -> Tuple[Dict[str, str], dict]:
    """Accepted files and a manifest from a ZIP's bytes. Raises IngestError for a bad archive."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, ValueError) as e:
        raise IngestError("that file isn't a valid ZIP archive") from e
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise IngestError(f"the archive has {len(infos):,} entries; the limit is {MAX_ZIP_ENTRIES:,}")
    skipped: Counter = Counter()
    skipped_dirs: Counter = Counter()
    entries = []
    for info in infos:
        if info.is_dir():
            continue
        rel = _safe_rel(info.filename)
        if rel is None:
            skipped["unsafe path"] += 1
            continue
        if stat.S_ISLNK(info.external_attr >> 16):
            skipped["symlink"] += 1
            continue
        if info.flag_bits & 0x1:
            skipped["encrypted"] += 1
            continue
        entries.append((rel, info))
    root = _common_root([r for r, _ in entries])
    budget = settings.max_upload_source_mb * 1024 * 1024
    read_budget = budget * 2  # decompressed bytes we'll inspect, accepted or not
    sources: Dict[str, str] = {}
    total = 0
    truncated = False
    for rel, info in sorted(entries, key=lambda e: e[0]):
        rel = rel[len(root):] if root and rel.startswith(root) else rel
        why = skip_reason(rel.replace("/", os.sep))
        if why:
            skipped[why] += 1
            if why == "generated":
                top = next((p for p in rel.split("/")[:-1] if skip_reason(os.path.join(p, "x"))), None)
                if top:
                    skipped_dirs[top + "/"] += 1
            continue
        if info.file_size > MAX_FILE_BYTES:
            skipped["too large"] += 1
            continue
        if len(sources) >= MAX_FILES or read_budget <= 0:
            truncated = True
            skipped["over limit"] += 1
            continue
        try:
            with zf.open(info) as f:
                raw = f.read(MAX_FILE_BYTES + 1)  # headers can lie about size
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError, EOFError):
            skipped["unreadable"] += 1
            continue
        read_budget -= len(raw)
        if len(raw) > MAX_FILE_BYTES:
            skipped["too large"] += 1
            continue
        if b"\0" in raw[:8192]:
            skipped["binary"] += 1
            continue
        text = raw.decode("utf-8", errors="ignore")
        if not text.strip():
            skipped["empty"] += 1
            continue
        if total + len(raw) > budget:
            truncated = True
            skipped["over limit"] += 1
            continue
        sources[rel] = text
        total += len(raw)
    if not sources:
        raise IngestError("no source files found in the archive (everything was filtered out)")
    project = name or (root.rstrip("/") if root else "") or "uploaded-project"
    return sources, build_manifest(project, sources, skipped, skipped_dirs, truncated)


# ── manifest ──────────────────────────────────────────────────────────────────
def build_manifest(name: str, sources: Dict[str, str], skipped: Counter,
                   skipped_dirs: Counter, truncated: bool) -> dict:
    langs: Counter = Counter()
    lang_bytes: Counter = Counter()
    for p, t in sources.items():
        lang = LANGUAGE.get(os.path.splitext(p)[1].lower(), "Other")
        langs[lang] += 1
        lang_bytes[lang] += len(t.encode("utf-8", "ignore"))
    paths = sorted(sources, key=lambda p: (p.count("/"), p))
    types = []
    for marker, kind in PROJECT_MARKERS:
        if any(p == marker or p.endswith("/" + marker) for p in paths) and kind not in types:
            types.append(kind)
    code = [p for p in paths if not TEST_FILE.search(p)]
    entries = [p for p in code if ENTRY_POINTS.search(p)]
    for p in code:
        rx = ENTRY_CODE.get(os.path.splitext(p)[1])
        if p not in entries and rx and rx.search(sources[p][:20000]):
            entries.append(p)
    return {
        "name": name[:200],
        "file_count": len(sources),
        "total_bytes": sum(len(t.encode("utf-8", "ignore")) for t in sources.values()),
        "languages": [{"language": k, "files": v, "bytes": lang_bytes[k]}
                      for k, v in sorted(langs.items(), key=lambda kv: (kv[0] == "Other", -kv[1]))],
        "project_types": types,
        "entry_points": entries[:12],
        "skipped": dict(skipped),
        "skipped_count": sum(skipped.values()),
        "skipped_dirs": [d for d, _ in skipped_dirs.most_common(8)],
        "truncated": truncated,
        "top_level": sorted({p.split("/", 1)[0] + ("/" if "/" in p else "") for p in paths})[:30],
    }


def pack(sources: Dict[str, str]) -> bytes:
    return gzip.compress(json.dumps(sources).encode(), compresslevel=6)


def unpack(blob: bytes) -> Dict[str, str]:
    return json.loads(gzip.decompress(blob))


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", name.strip().lower()).strip("-")[:120] or "project"


def upload_repo_id(user_id: str, name: str) -> str:
    """Same user + same project name → same repo, so a re-upload updates it in place."""
    return repo_id_for(f"{user_id}:upload:{slug(name)}")


# ── background jobs ───────────────────────────────────────────────────────────
_pool = ThreadPoolExecutor(max_workers=max(1, settings.max_concurrent_ingests),
                           thread_name_prefix="ingest-job")


# Each stage owns a slice of the bar, so progress only moves forward:
# reading 0–5 · chunking 5–10 · saving rows 10–30 · embedding 30–95 · done 100
STAGES = {"reading": (0, 5), "chunking": (5, 10), "saving": (10, 30), "embedding": (30, 95)}


def _stage_progress(stage: str, done: int, total: int) -> int:
    lo, hi = STAGES[stage]
    return lo + int((hi - lo) * min(done, total) / max(total, 1))


def _update(job_id: str, **fields) -> None:
    with dbmod.SessionLocal() as db:
        job = db.get(IngestJob, job_id)
        if job is None:
            return
        if "progress" in fields and fields.get("status", job.status) == "processing" \
                and job.status == "processing":
            # updates come from several threads and can land out of order: never go back
            fields["progress"] = max(job.progress or 0, fields["progress"])
        for k, v in fields.items():
            setattr(job, k, v)
        job.updated_at = time.time()
        db.commit()


def submit(job_id: str) -> None:
    _pool.submit(run_job, job_id)


def run_job(job_id: str) -> None:
    """Index a queued job's files into its repo; only changed files on a re-upload."""
    with dbmod.SessionLocal() as db:
        job = db.get(IngestJob, job_id)
        if job is None or job.status != "queued" or not job.payload:
            return
        user_id, repo_id, name, blob = job.user_id, job.repo_id, job.name, job.payload
        manifest = job.manifest or {}
    _update(job_id, status="processing", stage="reading", progress=0, detail="")
    t0 = time.time()
    try:
        sources = unpack(blob)
        roles = {p: detect_role(p, t) for p, t in sources.items()}
        meta = {"source": f"upload://{slug(name)}", "name": name, "branch": "", "kind": "upload",
                "commit": "", "indexed_at": time.time(), "roles": roles, "languages": _langs(roles),
                "manifest": {k: manifest.get(k) for k in ("project_types", "entry_points")}}
        backend = SqlBackend(repo_id, user_id)
        last = [0.0]

        lock = threading.Lock()

        # SQLite locks the whole file while the save transaction is open, so a progress
        # write from another connection would block; Postgres has no such problem
        sqlite = dbmod.engine.dialect.name == "sqlite"

        def progress(stage: str, done: int, total: int) -> None:
            if stage == "saving" and sqlite:
                return
            with lock:  # throttle: at most one write a second, plus each stage's last step
                now = time.monotonic()
                if now - last[0] < 1 and done < total:
                    return
                last[0] = now
                noun = "chunks embedded" if stage == "embedding" else "chunks saved"
                try:  # best effort: a missed progress write must never fail the job
                    _update(job_id, stage=stage, progress=_stage_progress(stage, done, total),
                            detail=f"{done:,}/{total:,} {noun}")
                except Exception as e:  # noqa: BLE001
                    log.debug("upload job %s: progress update skipped (%s)", job_id, e)

        backend.on_progress = progress
        store = RepoStore(repo_id, backend)
        old = dict(store.meta.get("file_hashes") or {})
        _update(job_id, stage="chunking", progress=_stage_progress("reading", 1, 1))
        if old:  # re-upload of the same project: only what changed
            new = {p: file_hash(t) for p, t in sources.items()}
            changes = {"added": sorted(set(new) - set(old)), "removed": sorted(set(old) - set(new)),
                       "modified": sorted(p for p in set(new) & set(old) if new[p] != old[p])}
            chunks = chunk_sources(sources, only=set(changes["added"]) | set(changes["modified"]))
            _update(job_id, stage="saving", progress=_stage_progress("chunking", 1, 1),
                    detail=f"{len(chunks):,} chunks")
            store.apply_changes(sources, meta, changes, chunks)
            if any(changes.values()):
                store.cache_clear("overview", "tasks")
        else:
            chunks = chunk_sources(sources)
            changes = {"added": sorted(sources), "removed": [], "modified": []}
            _update(job_id, stage="saving", progress=_stage_progress("chunking", 1, 1),
                    detail=f"{len(chunks):,} chunks")
            store.save(chunks, meta, sources)
        n = sum(len(v) for v in changes.values())
        _update(job_id, status="ready", stage="done", progress=100, payload=None,
                finished_at=time.time(),
                detail=f"{len(sources)} files indexed" + (f" · {n} changed" if old else ""))
        log.info("upload job %s ready: repo=%s files=%d chunks=%d in %.1fs", job_id, repo_id,
                 len(sources), len(store.chunks), time.time() - t0)
    except Exception as e:  # noqa: BLE001 — the job records the failure; the payload stays for retry
        log.exception("upload job %s failed", job_id)
        msg = str(e) if isinstance(e, IngestError) else "indexing failed unexpectedly; retry it"
        _update(job_id, status="failed", stage="failed", detail=msg[:500], finished_at=time.time())


def mark_if_stale(job: IngestJob) -> bool:
    """A worker that died (redeploy, crash) leaves a job 'processing' forever; fail it so the
    user can retry. Uses the heartbeat, so it's safe with several API replicas."""
    if job.status in ("queued", "processing") and time.time() - job.updated_at > STALE_AFTER:
        job.status, job.stage = "failed", "failed"
        job.detail = "the server restarted while indexing; retry it"
        job.updated_at = job.finished_at = time.time()
        return True
    return False


def job_out(job: IngestJob) -> dict:
    return {"job_id": job.id, "repo_id": job.repo_id, "name": job.name, "origin": job.origin,
            "status": job.status, "stage": job.stage, "progress": job.progress,
            "detail": job.detail, "manifest": job.manifest, "attempts": job.attempts,
            "can_retry": job.status == "failed" and job.payload is not None,
            "created_at": job.created_at, "updated_at": job.updated_at,
            "finished_at": job.finished_at}

