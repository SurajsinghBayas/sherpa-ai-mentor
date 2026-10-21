"""Private mode: code lives in memory only, expires, and access tokens are never kept."""
import base64
import subprocess
import time

import pytest


def _register(client, email="private@example.com"):
    r = client.post("/api/auth/register", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _db_counts(rid):
    import app.db as dbmod
    from app.dbmodels import RepoArtifact, RepoChunk, RepoFile
    with dbmod.SessionLocal() as db:
        return {m.__tablename__: db.query(m).filter(m.repo_id == rid).count()
                for m in (RepoFile, RepoChunk, RepoArtifact)}


@pytest.fixture(autouse=True)
def empty_registry():
    from app import private
    private._live.clear()
    yield
    private._live.clear()


@pytest.fixture()
def private_repo(client, monkeypatch, tmp_path):
    from app.config import settings
    monkeypatch.setattr(settings, "allow_local_ingest", True)
    h = _register(client)
    repo = tmp_path / "secret"
    repo.mkdir()
    (repo / "auth.py").write_text("def check_password(user, password):\n"
                                  "    return hash_password(password) == user.password_hash\n")
    (repo / "users.py").write_text("def create_user(email):\n    return {'email': email}\n")
    r = client.post("/api/ingest", json={"local_path": str(repo), "private": True}, headers=h)
    assert r.status_code == 200, r.text
    return h, r.json()


def test_private_repo_keeps_no_code_in_the_database(client, private_repo):
    import app.db as dbmod
    from app.dbmodels import Repo
    h, body = private_repo
    rid = body["repo_id"]
    assert body["private"] is True and body["expires_at"] > time.time()

    # usable: search, answers and the code viewer all work from memory
    r = client.post("/api/ask", json={"repo_id": rid, "question": "how is the password checked?"},
                    headers=h)
    assert r.status_code == 200 and "auth.py" in r.text
    f = client.get("/api/file", params={"repo_id": rid, "path": "auth.py"}, headers=h).json()
    assert f["lines"][0].startswith("def check_password")
    assert client.post("/api/overview", json={"repo_id": rid}, headers=h).status_code == 200

    # …yet no file text, chunk or generated output was written, and the row has no file list
    assert _db_counts(rid) == {"repo_files": 0, "repo_chunks": 0, "repo_artifacts": 0}
    with dbmod.SessionLocal() as db:
        row = db.get(Repo, rid)
        assert row.private and row.meta == {} and row.files_count == 2

    listed = client.get("/api/repos", headers=h).json()["repos"]
    assert [(x["repo_id"], x["private"]) for x in listed] == [(rid, True)]


def test_private_search_uses_in_memory_vectors(client, monkeypatch, tmp_path):
    """With embeddings on, vectors are computed per import and held only in the process."""
    from app import private
    from app.config import settings
    from app.embeddings import embedder

    def vec(text):  # 2-d toy space: "password" vs everything else
        return [1.0, 0.0] if "password" in text else [0.0, 1.0]

    monkeypatch.setattr(settings, "aws_bearer_token_bedrock", "fake")
    monkeypatch.setattr(type(embedder), "embed_documents",
                        lambda self, texts, on_progress=None: [vec(t) for t in texts])
    monkeypatch.setattr(type(embedder), "embed_query", lambda self, q: vec(q))
    monkeypatch.setattr(settings, "allow_local_ingest", True)
    h = _register(client, "vec@example.com")
    repo = tmp_path / "v"
    repo.mkdir()
    (repo / "auth.py").write_text("def verify(password):\n    return password == 'x'\n")
    (repo / "users.py").write_text("def create_user(email):\n    return email\n")
    rid = client.post("/api/ingest", json={"local_path": str(repo), "private": True},
                      headers=h).json()["repo_id"]
    store = private.get(rid)
    assert store.backend.vectors.shape == (2, 2)
    scores = store.backend.vector_scores("password", 2)
    best = max(scores, key=scores.get)
    assert store.chunks[best].file == "auth.py" and scores[best] == pytest.approx(1.0)


def test_private_and_normal_imports_of_one_source_are_separate(client, private_repo, tmp_path):
    h, body = private_repo
    normal = client.post("/api/ingest", json={"local_path": str(tmp_path / "secret")}, headers=h).json()
    assert normal["repo_id"] != body["repo_id"] and normal["private"] is False
    assert _db_counts(normal["repo_id"])["repo_chunks"] > 0
    assert _db_counts(body["repo_id"])["repo_chunks"] == 0


def test_expired_private_repo_is_wiped(client, private_repo):
    import app.db as dbmod
    from app import private
    from app.dbmodels import Repo
    h, body = private_repo
    rid = body["repo_id"]
    with dbmod.SessionLocal() as db:
        db.get(Repo, rid).expires_at = time.time() - 1
        db.commit()
    r = client.get("/api/file", params={"repo_id": rid, "path": "auth.py"}, headers=h)
    assert r.status_code == 410
    assert private.get(rid) is None
    assert client.get("/api/repos", headers=h).json()["repos"] == []


def test_sweeper_purges_expired_repos(client, private_repo):
    import app.db as dbmod
    from app import private
    from app.dbmodels import Repo
    _, body = private_repo
    rid = body["repo_id"]
    private.purge_expired()
    assert private.get(rid) is not None  # not yet due
    with dbmod.SessionLocal() as db:
        db.get(Repo, rid).expires_at = time.time() - 1
        db.commit()
    private.purge_expired()
    assert private.get(rid) is None
    with dbmod.SessionLocal() as db:
        assert db.get(Repo, rid) is None


def test_restart_drops_private_rows(client, private_repo):
    from app import private
    h, _ = private_repo
    private._live.clear()  # what a restart does to memory
    private.purge_orphans()
    assert client.get("/api/repos", headers=h).json()["repos"] == []


def test_delete_wipes_memory(client, private_repo):
    from app import private
    h, body = private_repo
    assert client.delete(f"/api/repos/{body['repo_id']}", headers=h).status_code == 204
    assert private.get(body["repo_id"]) is None


def test_private_repos_are_not_synced(client, private_repo):
    h, body = private_repo
    rid = body["repo_id"]
    assert client.post("/api/sync", json={"repo_id": rid}, headers=h).status_code == 422
    assert client.post(f"/api/repos/{rid}/check", headers=h).json()["status"] == "unsupported"


def test_token_forces_private_and_is_passed_only_to_the_clone(client, monkeypatch):
    import app.main as mainmod
    from app.chunk import Chunk
    h = _register(client, "tok@example.com")
    seen = {}

    def fake_ingest(url, local, branch="", token=""):
        seen["token"] = token
        meta = {"source": url, "name": "acme/secret", "kind": "git", "branch": "", "commit": "",
                "indexed_at": time.time(), "roles": {}, "languages": [".py"]}
        return "x", [Chunk(file="a.py", start_line=1, end_line=1, text="x = 1")], meta, {"a.py": "x = 1"}

    monkeypatch.setattr(mainmod, "ingest_source", fake_ingest)
    r = client.post("/api/ingest", json={"repo_url": "https://github.com/acme/secret",
                                         "token": "ghp_TESTTOKEN123"}, headers=h)
    assert r.status_code == 200 and r.json()["private"] is True
    assert seen["token"] == "ghp_TESTTOKEN123"
    assert "ghp_TESTTOKEN123" not in r.text


@pytest.mark.parametrize("payload", [
    {"local_path": "/tmp", "token": "abc"},                                   # token without a URL
    {"repo_url": "https://github.com/acme/secret", "token": "bad token\n"},   # header injection
])
def test_bad_token_requests_are_rejected(client, monkeypatch, payload):
    from app.config import settings
    monkeypatch.setattr(settings, "allow_local_ingest", True)
    h = _register(client, "bad@example.com")
    assert client.post("/api/ingest", json=payload, headers=h).status_code == 422


def test_clone_sends_token_as_header_not_in_args(monkeypatch):
    from app import ingest
    calls = {}

    def fake_run(cmd, **kw):
        calls["cmd"], calls["env"] = cmd, kw["env"]
        raise subprocess.CalledProcessError(128, cmd, stderr="fatal: Authentication failed")

    monkeypatch.setattr(ingest.subprocess, "run", fake_run)
    with pytest.raises(ingest.IngestError, match="token was rejected"):
        ingest.fetch_source("https://github.com/acme/secret", None, "", token="ghp_SECRET")
    assert not any("ghp_SECRET" in a for a in calls["cmd"])
    env = calls["env"]
    expected = base64.b64encode(b"x-access-token:ghp_SECRET").decode()
    assert env["GIT_CONFIG_VALUE_0"] == f"Authorization: Basic {expected}"
    assert (env["GIT_CONFIG_KEY_1"], env["GIT_CONFIG_VALUE_1"]) == ("http.followRedirects", "false")


def test_public_clone_has_no_auth_header(monkeypatch):
    from app import ingest
    assert ingest._token_env("https://github.com/acme/x", "") == {}
    assert "oauth2:" in base64.b64decode(
        ingest._token_env("https://gitlab.com/acme/x", "glpat")["GIT_CONFIG_VALUE_0"].split()[-1]).decode()


def test_token_without_repo_access_gets_a_clear_message(monkeypatch):
    """GitHub's 403 for a token lacking Contents access isn't a network problem."""
    from app import ingest

    def fake_run(cmd, **kw):
        raise subprocess.CalledProcessError(128, cmd, stderr=(
            "remote: Write access to repository not granted.\nfatal: unable to access "
            "'https://github.com/acme/x/': The requested URL returned error: 403"))

    monkeypatch.setattr(ingest.subprocess, "run", fake_run)
    with pytest.raises(ingest.IngestError, match="can't read this repository"):
        ingest.fetch_source("https://github.com/acme/x", None, "", token="ghp_x")
