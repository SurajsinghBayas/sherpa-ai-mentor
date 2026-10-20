#!/usr/bin/env python3
"""Sherpa CLI: upload a local codebase to Sherpa AI and ask about it from the terminal.

    sherpa login                      sign in with an email code (or --password)
    sherpa upload [PATH] [--name N]   zip the project, review what's included, index it
    sherpa status                     your recent uploads
    sherpa repos                      your indexed repositories
    sherpa ask REPO_ID "question"     a cited answer
    sherpa logout | whoami

Standard library only. Inside a git checkout only files git tracks or would track
(respecting .gitignore) are sent; dependencies, build output, secrets and binaries are
always left out. Config lives in ~/.config/sherpa/config.json (or SHERPA_API_URL /
SHERPA_TOKEN in the environment).
"""
from __future__ import annotations

import argparse
import getpass
import io
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile

__version__ = "0.1.0"
DEFAULT_API = "http://localhost:8000"
CONFIG = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
                      "sherpa", "config.json")

# keep in step with services/api/app/ingest.py (the server filters again regardless)
IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next",
               ".turbo", "coverage", ".pytest_cache", "vendor", "bower_components", "target",
               ".gradle", ".idea", ".mypy_cache", ".ruff_cache", ".tox", ".nuxt", ".svelte-kit",
               ".parcel-cache", ".terraform", "__MACOSX", ".hg", ".svn"}
SECRET_EXT = {".pem", ".key", ".p12", ".pfx", ".keystore", ".jks"}
IGNORE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".eot",
              ".mp4", ".pdf", ".zip", ".lock", ".db", ".sqlite", ".sqlite3", ".tsbuildinfo",
              ".class", ".jar", ".war", ".o", ".so", ".dll", ".exe", ".dylib", ".a", ".wasm", ".pyc",
              ".map", ".bin", ".dat", ".mp3", ".wav", ".webp", ".avif", ".bmp", ".tiff", ".psd",
              ".gz", ".tar", ".tgz", ".7z", ".rar", ".bz2", ".xz", ".iso", ".dmg", ".pkl", ".pt",
              ".onnx", ".h5", ".parquet", ".npy"} | SECRET_EXT
SECRET_FILES = {"id_rsa", "id_ed25519", ".npmrc", ".pypirc", ".netrc"}
IGNORE_FILES = {".DS_Store", "package-lock.json", "pnpm-lock.yaml"} | SECRET_FILES
ENV_TEMPLATES = (".example", ".sample", ".template", ".dist")
MAX_FILE_BYTES = 400_000
MAX_UPLOAD_BYTES = 100 * 1024 * 1024


class CliError(Exception):
    pass


# ── config & HTTP ─────────────────────────────────────────────────────────────
def load_config() -> dict:
    try:
        with open(CONFIG) as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    cfg["api"] = (os.environ.get("SHERPA_API_URL") or cfg.get("api") or DEFAULT_API).rstrip("/")
    cfg["token"] = os.environ.get("SHERPA_TOKEN") or cfg.get("token") or ""
    return cfg


def save_config(cfg: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    fd = os.open(CONFIG, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # holds a session token
    with os.fdopen(fd, "w") as f:
        json.dump({"api": cfg["api"], "token": cfg.get("token", "")}, f)


def call(cfg: dict, method: str, path: str, body=None, *, auth=True, raw: bytes = None,
         content_type: str = "application/json", timeout: float = 120):
    headers = {"Accept": "application/json", "User-Agent": f"sherpa-cli/{__version__}"}
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
    if data is not None:
        headers["Content-Type"] = content_type
    if auth:
        if not cfg.get("token"):
            raise CliError("not signed in; run `sherpa login`")
        headers["Authorization"] = f"Bearer {cfg['token']}"
    req = urllib.request.Request(cfg["api"] + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read().decode()
            return json.loads(text) if text else None
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode()).get("detail")
        except Exception:  # noqa: BLE001
            detail = None
        if e.code == 401 and auth:
            raise CliError("your session expired; run `sherpa login` again")
        raise CliError(f"{detail or e.reason} (HTTP {e.code})")
    except urllib.error.URLError as e:
        raise CliError(f"can't reach the Sherpa API at {cfg['api']} ({e.reason}); "
                       "set it with `sherpa login --api URL` or SHERPA_API_URL")


def multipart(fields: dict, file_field: str, filename: str, payload: bytes) -> tuple[bytes, str]:
    boundary = "sherpa-" + uuid.uuid4().hex
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    out.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
              f'filename="{filename}"\r\nContent-Type: application/zip\r\n\r\n'.encode())
    out.write(payload)
    out.write(f"\r\n--{boundary}--\r\n".encode())
    return out.getvalue(), f"multipart/form-data; boundary={boundary}"


# ── choosing files ────────────────────────────────────────────────────────────
def skip_reason(rel: str, size: int) -> str | None:
    parts = rel.split("/")
    name = parts[-1]
    if any(p in IGNORE_DIRS for p in parts[:-1]):
        return "generated"
    if name in IGNORE_FILES or name.startswith("._"):
        return "secret" if name in SECRET_FILES else "generated"
    if (name.startswith(".env") or name.endswith(".env")) and not name.endswith(ENV_TEMPLATES):
        return "secret"
    if name.endswith((".min.js", ".min.css")):
        return "generated"
    ext = os.path.splitext(name)[1].lower()
    if ext in IGNORE_EXT:
        return "secret" if ext in SECRET_EXT else "binary"
    if size > MAX_FILE_BYTES:
        return "too large"
    return None


def candidate_files(root: str) -> tuple[list[str], str]:
    """Relative paths to consider, and how they were found."""
    try:
        out = subprocess.run(["git", "-C", root, "ls-files", "-z", "--cached", "--others",
                              "--exclude-standard"], capture_output=True, timeout=60, check=True)
        files = [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p]
        if files:
            return files, "git (respecting .gitignore)"
    except (OSError, subprocess.SubprocessError):
        pass
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fn in filenames:
            found.append(os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/"))
    return found, "folder walk"


def build_zip(root: str, name: str) -> tuple[bytes, dict]:
    files, how = candidate_files(root)
    real_root = os.path.realpath(root)
    skipped: dict = {}
    kept = 0
    total = 0
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for rel in sorted(files):
            full = os.path.join(root, rel)
            # never follow symlinks out of the project
            if os.path.islink(full) or not os.path.isfile(full) or \
                    not os.path.realpath(full).startswith(real_root + os.sep):
                skipped["symlink/other"] = skipped.get("symlink/other", 0) + 1
                continue
            size = os.path.getsize(full)
            why = skip_reason(rel, size)
            if why:
                skipped[why] = skipped.get(why, 0) + 1
                continue
            with open(full, "rb") as f:
                data = f.read()
            if b"\0" in data[:8192]:
                skipped["binary"] = skipped.get("binary", 0) + 1
                continue
            z.writestr(f"{name}/{rel}", data)
            kept += 1
            total += size
    return buf.getvalue(), {"files": kept, "bytes": total, "skipped": skipped, "how": how}


# ── output helpers ────────────────────────────────────────────────────────────
def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


def bar(fraction: float, width: int = 28) -> str:
    filled = int(width * max(0.0, min(1.0, fraction)))
    return "█" * filled + "░" * (width - filled)


# ── commands ──────────────────────────────────────────────────────────────────
def cmd_login(args, cfg):
    if args.api:
        cfg["api"] = args.api.rstrip("/")
    email = args.email or input("Email: ").strip()
    if args.password:
        tok = call(cfg, "POST", "/api/auth/login",
                   {"email": email, "password": getpass.getpass("Password: ")}, auth=False)
    else:
        call(cfg, "POST", "/api/auth/otp/request", {"email": email, "purpose": "login"}, auth=False)
        print(f"We emailed a 6-digit code to {email}.")
        code = input("Code: ").strip()
        tok = call(cfg, "POST", "/api/auth/otp/verify",
                   {"email": email, "code": code, "purpose": "login"}, auth=False)
    cfg["token"] = tok["access_token"]
    save_config(cfg)
    me = call(cfg, "GET", "/api/auth/me")
    print(f"Signed in as {me['email']} on {cfg['api']}")


def cmd_logout(args, cfg):
    cfg["token"] = ""
    save_config(cfg)
    print("Signed out.")


def cmd_whoami(args, cfg):
    me = call(cfg, "GET", "/api/auth/me")
    print(f"{me['email']} on {cfg['api']}")


def cmd_upload(args, cfg):
    root = os.path.abspath(args.path)
    if not os.path.isdir(root):
        raise CliError(f"{args.path} is not a folder")
    name = (args.name or os.path.basename(root.rstrip(os.sep)) or "project").strip()
    print(f"Packing {root} …")
    payload, local = build_zip(root, name)
    if not local["files"]:
        raise CliError("no source files to upload (everything was dependencies, build output or binaries)")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise CliError(f"the packed project is {human(len(payload))}; the limit is "
                       f"{human(MAX_UPLOAD_BYTES)}. Upload a subfolder instead.")
    skipped = ", ".join(f"{v} {k}" for k, v in sorted(local["skipped"].items())) or "nothing"
    print(f"  {local['files']} files, {human(local['bytes'])} ({local['how']}); left out: {skipped}")
    print(f"Uploading {human(len(payload))} …")
    body, ctype = multipart({"name": name, "origin": "cli"}, "file", f"{name}.zip", payload)
    job = call(cfg, "POST", "/api/uploads", raw=body, content_type=ctype, timeout=600)
    m = job["manifest"]
    print(f"\n  Project      {job['name']}" + ("  (updates your earlier upload)" if job.get("updates_existing") else ""))
    print(f"  Files        {m['file_count']}  ·  {human(m['total_bytes'])}")
    print(f"  Type         {', '.join(m['project_types']) or '—'}")
    langs = ", ".join("%s (%d)" % (lang["language"], lang["files"]) for lang in m["languages"][:6])
    print(f"  Languages    {langs}")
    if m["entry_points"]:
        print(f"  Entry points {', '.join(m['entry_points'][:5])}")
    if m["truncated"]:
        print("  ! Large project: only the first files within the limit will be indexed.")
    if not args.yes and input("\nIndex it now? [Y/n] ").strip().lower() not in ("", "y", "yes"):
        call(cfg, "DELETE", f"/api/uploads/{job['job_id']}")
        print("Discarded.")
        return
    job = call(cfg, "POST", f"/api/uploads/{job['job_id']}/start")
    if args.no_wait:
        print(f"Indexing in the background. Check with `sherpa status` (job {job['job_id']}).")
        return
    wait(cfg, job)


def wait(cfg, job):
    last = ""
    while job["status"] in ("queued", "processing"):
        line = f"\r  {bar(job['progress'] / 100)} {job['progress']:3d}%  {job['stage']:<10} {job['detail'][:40]:<40}"
        if line != last and sys.stdout.isatty():
            sys.stdout.write(line)
            sys.stdout.flush()
            last = line
        time.sleep(1.2)
        job = call(cfg, "GET", f"/api/uploads/{job['job_id']}")
    if sys.stdout.isatty():
        sys.stdout.write("\r" + " " * 96 + "\r")
    if job["status"] == "ready":
        print(f"✓ {job['name']}: {job['detail']}")
        print(f"  repo id {job['repo_id']}  ·  try: sherpa ask {job['repo_id']} \"how does it start?\"")
    else:
        hint = " Run `sherpa retry " + job["job_id"] + "`." if job.get("can_retry") else ""
        raise CliError(f"indexing failed: {job['detail']}.{hint}")


def cmd_retry(args, cfg):
    wait(cfg, call(cfg, "POST", f"/api/uploads/{args.job_id}/start"))


def cmd_status(args, cfg):
    jobs = call(cfg, "GET", "/api/uploads")["uploads"]
    if not jobs:
        print("No uploads yet. Try `sherpa upload .`")
    for j in jobs:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(j["created_at"]))
        print(f"{j['job_id']}  {when}  {j['status']:<10} {j['progress']:3d}%  {j['name']}  {j['detail']}")


def cmd_repos(args, cfg):
    repos = call(cfg, "GET", "/api/repos")["repos"]
    if not repos:
        print("No repositories yet. Try `sherpa upload .`")
    for r in repos:
        print(f"{r['repo_id']}  {r['kind']:<7} {r['files']:>5} files  {r['name']}")


def cmd_ask(args, cfg):
    r = call(cfg, "POST", "/api/ask", {"repo_id": args.repo_id, "question": args.question}, timeout=300)
    print(r["answer_markdown"])
    if r.get("citations"):
        print("\nSources:")
        for c in r["citations"]:
            print(f"  {c['file']}:{c['start_line']}-{c['end_line']}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="sherpa", description="Upload a codebase to Sherpa AI and ask about it.")
    p.add_argument("--version", action="version", version=f"sherpa {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("login", help="sign in (email code by default)")
    s.add_argument("--api", help=f"API URL (default {DEFAULT_API})")
    s.add_argument("--email", help="your account email (asked if omitted)")
    s.add_argument("--password", action="store_true", help="use a password instead of an email code")
    s.set_defaults(fn=cmd_login)
    sub.add_parser("logout", help="forget the saved session").set_defaults(fn=cmd_logout)
    sub.add_parser("whoami", help="show the signed-in account").set_defaults(fn=cmd_whoami)
    s = sub.add_parser("upload", help="upload and index a local folder")
    s.add_argument("path", nargs="?", default=".", help="folder to upload (default: the current folder)")
    s.add_argument("--name", help="project name (default: the folder name); same name updates in place")
    s.add_argument("-y", "--yes", action="store_true", help="index without asking for confirmation")
    s.add_argument("--no-wait", action="store_true", help="return once indexing has started")
    s.set_defaults(fn=cmd_upload)
    s = sub.add_parser("retry", help="retry a failed upload without uploading again")
    s.add_argument("job_id", help="from `sherpa status` or the failed upload's message")
    s.set_defaults(fn=cmd_retry)
    sub.add_parser("status", help="your recent uploads").set_defaults(fn=cmd_status)
    sub.add_parser("repos", help="your indexed repositories").set_defaults(fn=cmd_repos)
    s = sub.add_parser("ask", help="ask a question about an indexed repository")
    s.add_argument("repo_id", help="from `sherpa repos` or the upload's output")
    s.add_argument("question", help="quote it, e.g. \"How does signup work?\"")
    s.set_defaults(fn=cmd_ask)
    args = p.parse_args(argv)
    try:
        args.fn(args, load_config())
    except CliError as e:
        print(f"sherpa: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
