"""Re-indexing: automatic (new commit → only changed files) and manual (full rebuild)."""
import pytest


def _register(client, email="re@example.com"):
    r = client.post("/api/auth/register", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _rows(rid):
    """{file: [(row id, ord)]} straight from the database."""
    import app.db as dbmod
    from app.dbmodels import RepoChunk
    out = {}
    with dbmod.SessionLocal() as db:
        for c in db.query(RepoChunk).filter(RepoChunk.repo_id == rid).order_by(RepoChunk.ord):
            out.setdefault(c.file, []).append((c.id, c.ord))
    return out


def _mark(rid, file):
    """Tag a file's chunk rows in place; only an untouched row keeps the tag."""
    import app.db as dbmod
    from app.dbmodels import RepoChunk
    with dbmod.SessionLocal() as db:
        db.query(RepoChunk).filter(RepoChunk.repo_id == rid, RepoChunk.file == file) \
            .update({RepoChunk.kind: "marked"})
        db.commit()


def _marked(rid):
    import app.db as dbmod
    from app.dbmodels import RepoChunk
    with dbmod.SessionLocal() as db:
        return {c.file for c in db.query(RepoChunk).filter(RepoChunk.repo_id == rid,
                                                           RepoChunk.kind == "marked")}


def _ingests_used():
    import app.db as dbmod
    from app.dbmodels import UsageCounter
    with dbmod.SessionLocal() as db:
        return sum(r.count for r in db.query(UsageCounter).filter(UsageCounter.kind == "ingest"))


@pytest.fixture()
def local_repo(client, monkeypatch, tmp_path):
    from app.config import settings
    monkeypatch.setattr(settings, "allow_local_ingest", True)
    h = _register(client)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def alpha():\n    return 1\n")
    (repo / "b.py").write_text("def beta():\n    return 2\n")
    (repo / "c.py").write_text("def gamma():\n    return 3\n")
    rid = client.post("/api/ingest", json={"local_path": str(repo)}, headers=h).json()["repo_id"]
    return h, repo, rid


def test_auto_check_reindexes_only_changed_files(client, local_repo):
    h, repo, rid = local_repo
    _mark(rid, "a.py")
    _mark(rid, "b.py")
    used = _ingests_used()
    # nothing changed → no work, no quota
    r = client.post(f"/api/repos/{rid}/check", headers=h).json()
    assert r["status"] == "up_to_date" and _ingests_used() == used

    (repo / "b.py").write_text("def beta():\n    return 'two'\n")
    (repo / "c.py").unlink()
    (repo / "d.py").write_text("def delta_handler():\n    return 4\n")
    r = client.post(f"/api/repos/{rid}/check", headers=h).json()
    assert r["status"] == "updated", r
    assert r["changes"] == {"added": ["d.py"], "modified": ["b.py"], "removed": ["c.py"]}
    assert r["files"] == 3 and _ingests_used() == used + 1

    after = _rows(rid)
    assert _marked(rid) == {"a.py"}                 # untouched file kept its rows; b.py rewritten
    assert "c.py" not in after and "d.py" in after
    f = client.get("/api/file", headers=h, params={"repo_id": rid, "path": "b.py"}).json()
    assert f["lines"][1] == "    return 'two'"
    assert client.get("/api/file", headers=h, params={"repo_id": rid, "path": "c.py"}).status_code == 404
    # search sees the new code
    from app.main import get_store
    import app.db as dbmod
    from app.dbmodels import User
    with dbmod.SessionLocal() as db:
        user = db.query(User).first()
        store = get_store(rid, user, db)
    assert store.search("delta handler", k=1)[0][0].file == "d.py"
    assert client.post(f"/api/repos/{rid}/check", headers=h).json()["status"] == "up_to_date"


def test_vector_positions_survive_gaps_in_chunk_numbering(client, local_repo):
    h, repo, rid = local_repo
    (repo / "a.py").unlink()  # leaves a gap at the front
    (repo / "e.py").write_text("def epsilon():\n    return 5\n")
    client.post(f"/api/repos/{rid}/check", headers=h)
    from app.persist import SqlBackend
    b = SqlBackend(rid)
    chunks, *_ = b.load()
    ords = [o for rows in _rows(rid).values() for _, o in rows]
    assert sorted(b._ord_index) == sorted(ords) and min(ords) > 0
    assert sorted(b._ord_index.values()) == list(range(len(chunks)))


def test_manual_reindex_rebuilds_everything(client, local_repo):
    h, repo, rid = local_repo
    before = _rows(rid)
    _mark(rid, "a.py")
    r = client.post("/api/sync", json={"repo_id": rid, "full": True}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["full"] is True and r.json()["repo_id"] == rid
    after = _rows(rid)
    assert set(after) == set(before)
    assert _marked(rid) == set()  # every row rewritten, even for unchanged files
    n = sum(len(rows) for rows in before.values())
    assert sorted(o for rows in after.values() for _, o in rows) == list(range(n))


def test_git_check_compares_commits_without_cloning(client, monkeypatch):
    import app.main as m
    h = _register(client)
    calls = {"head": 0, "fetch": 0}
    head = {"sha": "a" * 40}
    files = {"app.py": "def run():\n    return 1\n", "util.py": "X = 1\n"}

    def fake_head(url, branch=""):
        calls["head"] += 1
        return head["sha"]

    def fake_fetch(url, local, branch=""):
        calls["fetch"] += 1
        return dict(files), {"source": url, "name": "o/r", "branch": "", "commit": head["sha"],
                             "kind": "git", "indexed_at": 1.0, "roles": {}, "languages": [".py"]}

    def fake_ingest(url, local, branch=""):
        sources, meta = fake_fetch(url, local, branch)
        return "x", m.chunk_sources(sources), meta, sources

    monkeypatch.setattr(m, "remote_head", fake_head)
    monkeypatch.setattr(m, "fetch_source", fake_fetch)
    monkeypatch.setattr(m, "ingest_source", fake_ingest)
    m._last_check.clear()
    rid = client.post("/api/ingest", json={"repo_url": "https://github.com/o/r"}, headers=h).json()["repo_id"]
    calls["fetch"] = 0

    r = client.post(f"/api/repos/{rid}/check", headers=h).json()
    assert r["status"] == "up_to_date" and calls == {"head": 1, "fetch": 0}  # no clone

    head["sha"] = "b" * 40
    files["util.py"] = "X = 2\n"
    m._last_check.clear()
    r = client.post(f"/api/repos/{rid}/check", headers=h).json()
    assert r["status"] == "updated" and r["commit"] == "b" * 40 and r["previous_commit"] == "a" * 40
    assert r["changes"] == {"added": [], "modified": ["util.py"], "removed": []}
    assert calls["fetch"] == 1
    # within the check interval the remote isn't asked again
    client.post(f"/api/repos/{rid}/check", headers=h)
    assert calls["head"] == 2


def test_check_reports_quota_instead_of_failing(client, local_repo, monkeypatch):
    from app.config import settings
    h, repo, rid = local_repo
    monkeypatch.setattr(settings, "daily_ingests", 1)  # the initial ingest used it
    (repo / "a.py").write_text("def alpha():\n    return 'changed'\n")
    r = client.post(f"/api/repos/{rid}/check", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "outdated" and "limit" in r.json()["detail"]


def test_check_is_owner_scoped(client, local_repo):
    _, _, rid = local_repo
    other = _register(client, "other@example.com")
    assert client.post(f"/api/repos/{rid}/check", headers=other).status_code == 404
