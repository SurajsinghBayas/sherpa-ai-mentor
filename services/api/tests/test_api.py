"""API-level tests: ingest safety, file viewer, body limit, study workflow."""
import os


def _register(client, email="study@example.com"):
    r = client.post("/api/auth/register", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_ingest_rejects_non_https_and_lookalike_hosts(client):
    h = _register(client)
    assert client.post("/api/ingest", json={"repo_url": "https://github.com/a/b"}).status_code == 401
    for url in ("http://github.com/a/b", "https://github.com.evil.io/a/b",
                "https://evilgithub.com/a/b", "https://169.254.169.254/x"):
        assert client.post("/api/ingest", json={"repo_url": url}, headers=h).status_code == 422, url


def test_local_ingest_disabled_by_default(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "allow_local_ingest", False)
    h = _register(client)
    assert client.post("/api/ingest", json={"local_path": "/etc"}, headers=h).status_code == 403
    assert client.post("/api/ingest-self", headers=h).status_code == 403


def test_local_ingest_skips_secrets_and_serves_files(client, monkeypatch, tmp_path):
    from app.config import settings
    monkeypatch.setattr(settings, "allow_local_ingest", True)
    h = _register(client)
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "app.py").write_text("def hello():\n    return 'hi'\n")
    (repo / ".env").write_text("SECRET=1\n")
    (repo / ".env.example").write_text("SECRET=\n")
    (repo / "local.db").write_bytes(b"SQLite format 3\x00\x00")
    r = client.post("/api/ingest", json={"local_path": str(repo)}, headers=h)
    assert r.status_code == 200, r.text
    rid = r.json()["repo_id"]
    f = client.get("/api/file", headers=h, params={"repo_id": rid, "path": "pkg/app.py"}).json()
    assert f["lines"][0] == "def hello():"
    assert client.get("/api/file", headers=h, params={"repo_id": rid, "path": ".env"}).status_code == 404
    assert client.get("/api/file", headers=h, params={"repo_id": rid, "path": "local.db"}).status_code == 404
    # re-ingest after an edit reports the change
    (repo / "pkg" / "app.py").write_text("def hello():\n    return 'hello'\n")
    r2 = client.post("/api/sync", json={"repo_id": rid}, headers=h).json()
    assert r2["changes"]["modified"] == ["pkg/app.py"]


def test_body_limit_returns_413(client):
    r = client.post("/api/ask", content=b"x" * (2 * 1024 * 1024),
                    headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_study_workflow(client):
    h = _register(client)
    assert client.post("/api/study/results", json={}, headers=h).status_code == 422
    rows = [("P1", "control", 900, 2), ("P2", "control", 1100, 2),
            ("P3", "sherpa", 400, 3), ("P4", "sherpa", 500, 3)]
    for p, g, sec, sc in rows:
        r = client.post("/api/study/results", headers=h, json={
            "participant": p, "group": g, "task": "architecture", "seconds": sec, "score": sc,
            "useful": 5 if g == "sherpa" else 0})
        assert r.status_code == 201, r.text
    s = client.get("/api/study/summary", headers=h).json()
    arch = next(t for t in s["tasks"] if t["task"] == "architecture")
    assert arch["control"]["mean_minutes"] == 16.7 and arch["sherpa"]["mean_minutes"] == 7.5
    assert arch["time_saved_pct"] == 55
    assert "participant,group" in client.get("/api/study/results.csv", headers=h).text
    # results are private to the facilitator who recorded them
    other = _register(client, "other@example.com")
    assert client.get("/api/study/results", headers=other).json() == []
    assert client.get("/api/study/results").status_code == 401


def test_production_refuses_unsafe_settings():
    from app.config import Settings, production_problems
    dev = Settings(environment="development")
    assert production_problems(dev) == []
    bad = Settings(environment="production", jwt_secret_key="dev-only-change-me", encryption_key="",
                   database_url="", allow_local_ingest=True, allowed_origins="*")
    assert len(production_problems(bad)) == 5
    from cryptography.fernet import Fernet
    good = Settings(environment="production", jwt_secret_key="x" * 48,
                    encryption_key=Fernet.generate_key().decode(),
                    database_url="postgresql+psycopg://u:p@h/db", allow_local_ingest=False,
                    allowed_origins="https://sherpa.example.com")
    assert production_problems(good) == []


def test_migrations_create_schema(tmp_path, monkeypatch):
    """Alembic builds the full schema from scratch (what a fresh cloud database gets)."""
    import app.db as dbmod
    from sqlalchemy import create_engine, inspect
    eng = create_engine(f"sqlite:///{tmp_path}/m.db")
    monkeypatch.setattr(dbmod, "engine", eng)
    dbmod.init_db()
    dbmod.init_db()  # idempotent
    tables = set(inspect(eng).get_table_names())
    assert {"users", "repos", "repo_chunks", "repo_files", "repo_artifacts", "usage_counters",
            "study_results", "alembic_version"} <= tables


def test_init_db_recreates_missing_tables(tmp_path, monkeypatch):
    """A table dropped behind Alembic's back (version still at head) comes back on startup."""
    import app.db as dbmod
    from sqlalchemy import create_engine, inspect
    eng = create_engine(f"sqlite:///{tmp_path}/r.db")
    monkeypatch.setattr(dbmod, "engine", eng)
    dbmod.init_db()
    with eng.begin() as conn:
        conn.exec_driver_sql("DROP TABLE ingest_jobs")
        conn.exec_driver_sql("DROP TABLE study_results")
    dbmod.init_db()
    tables = set(inspect(eng).get_table_names())
    assert {"ingest_jobs", "study_results"} <= tables
    assert dbmod.vectors_ready is False  # SQLite: no pgvector, search uses TF-IDF
