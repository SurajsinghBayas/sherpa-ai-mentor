"""Commit history for Repo City's time-lapse: which files each commit added, changed or deleted.

Indexing clones only the latest commit, so history is fetched separately, the first time the
city is opened: a clone with commits and trees but no file contents (`--filter=blob:none`),
limited to the last MAX_COMMITS commits. For large repos that is a few MB instead of the full
history. The result is cached per indexed commit. Uploads and repos that can't be cloned again
(private repos: their token is never stored) have no history; the city then shows today only.
"""
import logging
import os
import shutil
import subprocess
import tempfile
import time

from .config import settings
from .ingest import _GIT_ENV, _GIT_SAFE

log = logging.getLogger(__name__)

MAX_COMMITS = 800
REC, FIELD = "\x1e", "\x1f"


def _parse(log_text: str) -> list[dict]:
    """`git log --name-status` with our record/field separators → commits, oldest first."""
    commits = []
    for rec in log_text.split(REC):
        rec = rec.strip("\n")
        if not rec:
            continue
        head, _, body = rec.partition("\n")
        parts = head.split(FIELD)
        if len(parts) < 3:
            continue
        sha, at, subject = parts[0], parts[1], parts[2]
        files = []
        for line in body.splitlines():
            bits = line.split("\t")
            if len(bits) >= 2 and bits[0][:1] in "AMDT":
                files.append([bits[0][:1], bits[-1]])
        try:
            t = int(at)
        except ValueError:
            continue
        commits.append({"sha": sha[:10], "t": t, "subject": subject[:140], "files": files})
    commits.reverse()
    return commits


def _git_log(git_dir_args: list[str], timeout: int) -> str:
    cmd = ["git", *_GIT_SAFE, *git_dir_args, "log", "--no-merges", "--no-renames", "--name-status",
           f"-n{MAX_COMMITS}", f"--format={REC}%H{FIELD}%at{FIELD}%s"]
    return subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, **_GIT_ENV}).stdout


def fetch_history(meta: dict) -> dict | None:
    """{"commits": [...], "truncated": bool} or None when this source has no reachable history."""
    source, kind = meta.get("source") or "", meta.get("kind")
    started = time.time()
    try:
        if kind == "git" and source.startswith("https://"):
            tmp = tempfile.mkdtemp(prefix="sherpa-hist-")
            try:
                dest = os.path.join(tmp, "repo")
                cmd = ["git", *_GIT_SAFE, "clone", "--filter=blob:none", "--no-checkout", "--bare",
                       f"--depth={MAX_COMMITS}", "--single-branch", "--no-tags"]
                if meta.get("branch"):
                    cmd += ["--branch", meta["branch"]]
                subprocess.run(cmd + ["--", source, dest], check=True, capture_output=True, text=True,
                               timeout=settings.clone_timeout_seconds, env={**os.environ, **_GIT_ENV})
                out = _git_log(["--git-dir", dest], settings.clone_timeout_seconds)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        elif kind == "local" and settings.allow_local_ingest and os.path.isdir(os.path.join(source, ".git")):
            out = _git_log(["-C", source], 60)
        else:
            return None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        err = getattr(e, "stderr", "") or str(e)
        log.warning("history: unavailable for %s (%s)", meta.get("name"), str(err).strip()[:200])
        return None
    commits = _parse(out)
    log.info("history: %d commits for %s in %.1fs", len(commits), meta.get("name"), time.time() - started)
    return {"commits": commits, "truncated": len(commits) >= MAX_COMMITS}
