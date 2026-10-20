"""Production guardrails: SSRF, git source validation, symlinks, rate limits, ingest slots."""
import os

import pytest
from fastapi import HTTPException


def _register(client, email="guard@example.com"):
    r = client.post("/api/auth/register", json={"email": email, "password": "password123"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def production(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "environment", "production")
    return settings


# ── git sources ──────────────────────────────────────────────────────────────
def test_repo_urls_are_normalised_or_rejected():
    from app.guards import normalize_repo_url
    assert normalize_repo_url(" https://GitHub.com/tiangolo/full-stack-fastapi-template/ ") == \
        "https://github.com/tiangolo/full-stack-fastapi-template"
    assert normalize_repo_url("https://github.com/a/b/tree/main/src") == "https://github.com/a/b"
    assert normalize_repo_url("https://gitlab.com/group/sub/proj.git") == "https://gitlab.com/group/sub/proj.git"
    for bad in ("https://user:tok@github.com/a/b", "https://github.com:8443/a/b", "https://github.com/a",
                "https://github.com/a/b?x=1#y", "https://github.com/../etc/passwd", "ssh://github.com/a/b",
                "file:///etc", "https://github.com/a/b%0a"):
        with pytest.raises(HTTPException):
            normalize_repo_url(bad) if "?" not in bad else _strict(bad)


def _strict(url):
    # query/fragment are dropped, never passed to git; make the test assert that explicitly
    from app.guards import normalize_repo_url
    out = normalize_repo_url(url)
    assert "?" not in out and "#" not in out
    raise HTTPException(422, "ok")


def test_branch_names_cannot_become_git_options():
    from app.guards import check_branch
    assert check_branch(" release/1.2 ") == "release/1.2"
    assert check_branch("") == ""
    for bad in ("--upload-pack=touch /tmp/x", "-b", "a..b", "a b", "a;rm -rf /"):
        with pytest.raises(HTTPException):
            check_branch(bad)


def test_symlinks_in_a_repo_are_never_read(client, monkeypatch, tmp_path):
    from app.config import settings
    monkeypatch.setattr(settings, "allow_local_ingest", True)
    h = _register(client)
    secret = tmp_path / "outside.txt"
    secret.write_text("TOP_SECRET=1\n")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')\n")
    os.symlink(secret, repo / "leak.py")
    os.symlink(tmp_path, repo / "parent")  # symlinked directory
    rid = client.post("/api/ingest", json={"local_path": str(repo)}, headers=h).json()["repo_id"]
    for path in ("leak.py", "parent/outside.txt"):
        assert client.get("/api/file", headers=h, params={"repo_id": rid, "path": path}).status_code == 404


# ── outbound URLs (custom LLM endpoints) ─────────────────────────────────────
def test_endpoints_must_be_public_https_in_production(client, production):
    h = _register(client)
    for url in ("http://1.1.1.1/v1", "https://127.0.0.1/v1", "https://169.254.169.254/latest",
                "https://10.0.0.5/v1", "https://[::1]/v1", "https://user:pw@1.1.1.1/v1",
                "https://localhost/v1"):
        r = client.post("/api/endpoints", headers=h, json={
            "name": "x", "base_url": url, "kind": "openai-compatible", "model": "m"})
        assert r.status_code == 422, url
        assert client.post("/api/endpoints/test", headers=h, json={
            "name": "x", "base_url": url, "kind": "openai-compatible"}).status_code == 422, url
    ok = client.post("/api/endpoints", headers=h, json={
        "name": "x", "base_url": "https://1.1.1.1/v1", "kind": "openai-compatible", "model": "m"})
    assert ok.status_code == 201, ok.text


def test_local_endpoints_still_work_in_development(client):
    h = _register(client)
    r = client.post("/api/endpoints", headers=h, json={
        "name": "ollama", "base_url": "http://localhost:11434", "kind": "ollama", "model": "llama3"})
    assert r.status_code == 201, r.text


# ── rate limits ──────────────────────────────────────────────────────────────
def test_password_login_is_rate_limited(client):
    codes = [client.post("/api/auth/login", json={"email": "x@example.com", "password": "nope12345"}).status_code
             for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    r = client.post("/api/auth/login", json={"email": "x@example.com", "password": "nope12345"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0


def test_code_requests_are_rate_limited_per_ip(client, monkeypatch):
    import app.routers.auth as auth
    monkeypatch.setattr(auth, "mail_configured", lambda: True)
    monkeypatch.setattr(auth, "send_mail", lambda *a: None)
    codes = [client.post("/api/auth/otp/request", json={"email": f"u{i}@example.com", "purpose": "signup"}).status_code
             for i in range(6)]
    assert codes == [200] * 5 + [429]


def test_limiter_prunes_and_resets():
    from app.guards import RateLimiter
    lim = RateLimiter()
    assert [lim.hit("k", 2, 60) for _ in range(3)][-1] > 0
    assert lim.hit("k", 2, 0) == 0  # window elapsed → counter resets


# ── ingest slots ─────────────────────────────────────────────────────────────
def test_one_import_per_user_at_a_time():
    from app.main import _IngestSlot
    with _IngestSlot("u1"):
        with pytest.raises(HTTPException) as e:
            with _IngestSlot("u1"):
                pass
        assert e.value.status_code == 409
        with _IngestSlot("u2"):  # other users are not blocked
            pass
    with _IngestSlot("u1"):  # released after use
        pass


def test_server_wide_import_cap(monkeypatch):
    import threading
    import app.main as m
    monkeypatch.setattr(m, "_ingest_slots", threading.BoundedSemaphore(1))
    with m._IngestSlot("a"):
        monkeypatch.setattr(m._ingest_slots, "acquire", lambda timeout: False)
        with pytest.raises(HTTPException) as e:
            with m._IngestSlot("b"):
                pass
        assert e.value.status_code == 503
    assert "b" not in m._ingesting


# ── HTTP plumbing ────────────────────────────────────────────────────────────
def test_ready_request_id_and_no_store(client):
    assert client.get("/ready").json() == {"ok": True}
    h = _register(client)
    r = client.get("/api/repos", headers={**h, "X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123" and r.headers["Cache-Control"] == "no-store"


def test_chunked_body_over_limit_is_rejected(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "max_body_bytes", 1000)
    h = _register(client)

    def body():
        for _ in range(10):
            yield b"x" * 500

    r = client.post("/api/ask", content=body(), headers={**h, "content-type": "application/json"})
    assert r.status_code == 413


def test_production_config_checks():
    from cryptography.fernet import Fernet
    from app.config import Settings, production_problems
    base = dict(environment="production", jwt_secret_key="j" * 48,
                encryption_key=Fernet.generate_key().decode(),
                database_url="postgresql+psycopg://u:p@db.example.com/db",
                allowed_origins="https://sherpa.example.com")
    assert production_problems(Settings(**base)) == []
    for override, needle in ((dict(encryption_key="not-a-key"), "valid Fernet"),
                             (dict(encryption_key="j" * 48), "Fernet"),
                             (dict(database_url="sqlite:///x.db"), "Postgres"),
                             (dict(database_url="postgresql+psycopg://u:p@db.example.com/db?sslmode=disable"), "SSL"),
                             (dict(allowed_origins="http://sherpa.example.com"), "https"),
                             (dict(rate_limits_enabled=False), "RATE_LIMITS")):
        problems = production_problems(Settings(**{**base, **override}))
        assert any(needle in p for p in problems), (override, problems)


def test_system_prompt_ships_with_the_api_and_resists_injection():
    from app.agents.common import SYSTEM_PROMPT
    assert "untrusted" in SYSTEM_PROMPT and "Never reveal" in SYSTEM_PROMPT
