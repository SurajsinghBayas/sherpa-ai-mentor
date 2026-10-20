"""Uploading a codebase from the user's device (ZIP / folder / CLI) as a background job."""
import io
import stat
import time
import zipfile

import pytest


def _register(client, email="up@example.com"):
    r = client.post("/api/auth/register", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _zip(files: dict, root: str = "shop-main/", method=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", method) as z:
        for path, data in files.items():
            z.writestr(root + path, data)
    return buf.getvalue()


PROJECT = {
    "app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n\n@app.post('/signup')\ndef signup():\n    return {}\n",
    "app/crud.py": "def create_user(email):\n    return email\n",
    "requirements.txt": "fastapi\n",
    "web/package.json": '{"name": "web"}\n',
    "web/src/index.tsx": "export const App = () => null;\n",
    ".env": "SECRET=1\n",
    ".env.example": "SECRET=\n",
    ".github/workflows/ci.yml": "on: push\n",
    "node_modules/react/index.js": "module.exports = {};\n",
    ".git/config": "[core]\n",
    "web/dist/bundle.min.js": "var a=1;\n",
    "logo.png": b"\x89PNG\r\n\x1a\n\x00\x00",
    "big.py": "x = 1\n" * 100_000,
}


@pytest.fixture(autouse=True)
def run_jobs_inline(monkeypatch):
    """Run background jobs synchronously so tests can assert on the result."""
    import app.uploads as up
    monkeypatch.setattr(up, "submit", up.run_job)


# ── reading archives ─────────────────────────────────────────────────────────
def test_zip_is_filtered_and_described():
    from app.uploads import read_zip
    sources, m = read_zip(_zip(PROJECT))
    assert set(sources) == {"app/main.py", "app/crud.py", "requirements.txt", "web/package.json",
                            "web/src/index.tsx", ".env.example", ".github/workflows/ci.yml"}
    assert m["name"] == "shop-main" and m["file_count"] == 7
    assert {"Python", "Node.js"} <= set(m["project_types"])
    assert "app/main.py" in m["entry_points"] and "web/src/index.tsx" in m["entry_points"]
    assert m["skipped"]["secret"] == 1 and m["skipped"]["too large"] == 1 and m["skipped"]["binary"] == 1
    assert {"node_modules/", ".git/"} <= set(m["skipped_dirs"])
    assert m["languages"][0]["language"] == "Python"


def test_hostile_archive_entries_are_skipped():
    from app.uploads import read_zip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ok.py", "print(1)\n")
        z.writestr("../escape.py", "print('pwned')\n")
        z.writestr("/abs/path.py", "print('pwned')\n")
        z.writestr("C:/win.py", "print('pwned')\n")
        link = zipfile.ZipInfo("link.py")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(link, "/etc/passwd")
    sources, m = read_zip(buf.getvalue(), "evil")
    assert set(sources) == {"ok.py"}
    assert m["skipped"]["unsafe path"] == 3 and m["skipped"]["symlink"] == 1


def test_size_header_that_lies_is_still_capped(monkeypatch):
    import app.uploads as up
    monkeypatch.setattr(up, "MAX_FILE_BYTES", 10)
    sources, m = up.read_zip(_zip({"a.py": "x = 1\n", "b.py": "y = 'a long line of code'\n"}))
    assert set(sources) == {"a.py"} and m["skipped"]["too large"] == 1


def test_file_count_cap_marks_truncated(monkeypatch):
    import app.uploads as up
    monkeypatch.setattr(up, "MAX_FILES", 2)
    sources, m = up.read_zip(_zip({f"m{i}.py": f"x = {i}\n" for i in range(5)}))
    assert len(sources) == 2 and m["truncated"] and m["skipped"]["over limit"] == 3


def test_not_a_zip_and_nothing_usable():
    from app.ingest import IngestError
    from app.uploads import read_zip
    with pytest.raises(IngestError):
        read_zip(b"definitely not a zip")
    with pytest.raises(IngestError):
        read_zip(_zip({"node_modules/x.js": "1\n", "a.png": b"\x00\x01"}))


# ── API flow ─────────────────────────────────────────────────────────────────
def _upload(client, h, files=PROJECT, name="", origin="zip", data=None):
    return client.post("/api/uploads", headers=h,
                       files={"file": ("shop.zip", data if data is not None else _zip(files), "application/zip")},
                       data={"name": name, "origin": origin})


def test_upload_review_then_index(client):
    h = _register(client)
    r = _upload(client, h)
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["status"] == "review" and job["manifest"]["file_count"] == 7 and not job["updates_existing"]
    assert client.get("/api/repos", headers=h).json()["repos"] == []  # nothing indexed before confirm

    started = client.post(f"/api/uploads/{job['job_id']}/start", headers=h).json()
    assert started["status"] == "ready" and started["progress"] == 100 and not started["can_retry"]
    repos = client.get("/api/repos", headers=h).json()["repos"]
    assert [(x["name"], x["kind"], x["files"]) for x in repos] == [("shop-main", "upload", 7)]
    rid = repos[0]["repo_id"]
    f = client.get("/api/file", headers=h, params={"repo_id": rid, "path": "app/crud.py"}).json()
    assert f["lines"][0] == "def create_user(email):"
    ans = client.post("/api/ask", headers=h, json={"repo_id": rid, "question": "how does signup work?"})
    assert ans.status_code == 200 and ans.json()["citations"]
    # uploads have no remote: auto-check says so, sync explains how to update
    assert client.post(f"/api/repos/{rid}/check", headers=h).json()["status"] == "unsupported"
    assert client.post("/api/sync", headers=h, json={"repo_id": rid}).status_code == 422
    # starting twice is refused
    assert client.post(f"/api/uploads/{job['job_id']}/start", headers=h).status_code == 409


def test_reupload_updates_only_changed_files(client):
    h = _register(client)
    first = _upload(client, h).json()
    client.post(f"/api/uploads/{first['job_id']}/start", headers=h)
    changed = dict(PROJECT, **{"app/crud.py": "def create_user(email, name):\n    return email\n"})
    second = _upload(client, h, changed).json()
    assert second["updates_existing"] and second["repo_id"] == first["repo_id"]
    done = client.post(f"/api/uploads/{second['job_id']}/start", headers=h).json()
    assert done["status"] == "ready" and "1 changed" in done["detail"]
    assert len(client.get("/api/repos", headers=h).json()["repos"]) == 1


def test_failed_job_can_be_retried_without_reupload(client, monkeypatch):
    import app.uploads as up
    h = _register(client)
    job = _upload(client, h).json()
    real = up.chunk_sources
    calls = {"n": 0}

    def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("embedding service down")
        return real(*a, **kw)

    monkeypatch.setattr(up, "chunk_sources", flaky)
    failed = client.post(f"/api/uploads/{job['job_id']}/start", headers=h).json()
    assert failed["status"] == "failed" and failed["can_retry"] and "retry" in failed["detail"]
    ok = client.post(f"/api/uploads/{job['job_id']}/start", headers=h).json()
    assert ok["status"] == "ready" and ok["attempts"] == 2


def test_upload_limits_and_errors(client, monkeypatch):
    from app.config import settings
    h = _register(client)
    assert _upload(client, h, data=b"not a zip").status_code == 422
    assert _upload(client, h, data=b"").status_code == 422
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    big = _zip({f"f{i}.txt": __import__("os").urandom(200_000).hex() for i in range(4)}, root="",
               method=zipfile.ZIP_STORED)
    assert len(big) > 1024 * 1024
    assert _upload(client, h, data=big).status_code == 413
    assert client.post("/api/uploads", files={"file": ("a.zip", _zip(PROJECT))}).status_code == 401


def test_uploads_are_private(client):
    h = _register(client)
    job = _upload(client, h).json()
    other = _register(client, "other@example.com")
    assert client.get(f"/api/uploads/{job['job_id']}", headers=other).status_code == 404
    assert client.post(f"/api/uploads/{job['job_id']}/start", headers=other).status_code == 404
    assert client.get("/api/uploads", headers=other).json()["uploads"] == []
    assert len(client.get("/api/uploads", headers=h).json()["uploads"]) == 1


def test_dead_worker_jobs_become_retryable(client):
    import app.db as dbmod
    from app.dbmodels import IngestJob
    h = _register(client)
    job = _upload(client, h).json()
    with dbmod.SessionLocal() as db:
        j = db.get(IngestJob, job["job_id"])
        j.status, j.updated_at = "processing", time.time() - 3600
        db.commit()
    r = client.get(f"/api/uploads/{job['job_id']}", headers=h).json()
    assert r["status"] == "failed" and r["can_retry"]


def test_one_running_upload_per_user(client):
    import app.db as dbmod
    from app.dbmodels import IngestJob
    h = _register(client)
    a = _upload(client, h).json()
    b = _upload(client, h, name="other").json()
    with dbmod.SessionLocal() as db:
        db.get(IngestJob, a["job_id"]).status = "processing"
        db.get(IngestJob, a["job_id"]).updated_at = time.time()
        db.commit()
    assert client.post(f"/api/uploads/{b['job_id']}/start", headers=h).status_code == 409
    assert client.delete(f"/api/uploads/{a['job_id']}", headers=h).status_code == 409
    assert client.delete(f"/api/uploads/{b['job_id']}", headers=h).status_code == 204


def test_progress_only_moves_forward(client):
    import app.db as dbmod
    import app.uploads as up
    from app.dbmodels import IngestJob
    h = _register(client)
    job = _upload(client, h).json()
    with dbmod.SessionLocal() as db:
        db.get(IngestJob, job["job_id"]).status = "processing"
        db.commit()
    for value in (40, 70, 55, 65, 90):  # embedding threads can report out of order
        up._update(job["job_id"], stage="embedding", progress=value)
    assert client.get(f"/api/uploads/{job['job_id']}", headers=h).json()["progress"] == 90
    # stages own consecutive slices of the bar
    ends = [up._stage_progress(s, 1, 1) for s in ("reading", "chunking", "saving", "embedding")]
    starts = [up._stage_progress(s, 0, 1) for s in ("reading", "chunking", "saving", "embedding")]
    assert ends == sorted(ends) and all(e == s2 for e, s2 in zip(ends, starts[1:]))


def test_cli_is_served_preset_to_this_server(client):
    import os
    r = client.get("/cli/sherpa.py")
    assert r.status_code == 200 and r.text.startswith("#!/usr/bin/env python3")
    assert "DEFAULT_API = 'http://testserver'" in r.text  # downloads talk to this API
    # the bundled copy must match cli/sherpa_cli.py (run `make cli-sync` after editing the CLI)
    here = os.path.dirname(__file__)
    src = os.path.join(here, "..", "..", "..", "cli", "sherpa_cli.py")
    if os.path.exists(src):
        with open(src) as a, open(os.path.join(here, "..", "app", "static", "sherpa_cli.py")) as b:
            assert a.read() == b.read(), "bundled CLI is out of date: run `make cli-sync`"


def test_desktop_app_origin_allowed(client):
    """The Tauri app (tauri://localhost) can call the API; an unknown origin can't."""
    ok = client.options("/api/health", headers={"Origin": "tauri://localhost", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "tauri://localhost"
    bad = client.options("/api/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers
