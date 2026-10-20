"""Pipeline tests: citation verifier, static analysis, living docs, LLM fallback chain."""
import logging

from app.agents.common import verify_citations
from app.chunk import chunk_file
from app.store import RepoStore

SRC = {
    "app/main.py": "from fastapi import FastAPI\nfrom .routes import users\n\napp = FastAPI()\napp.include_router(users.router)\n",
    "app/routes/users.py": "from ..core import security\n\n\ndef signup(email, password):\n    # TODO: validate email format before hashing\n    return security.hash_password(password)\n",
    "app/core/security.py": "def hash_password(p):\n    return 'x' + p\n",
    "app/__init__.py": "\n",
    "app/routes/__init__.py": "\n",
    "app/core/__init__.py": "\n",
    "README.md": "# Demo\n\n## Setup\n\nRun `uvicorn app.main:app`.\n",
}


def make_store(tmp_path, src=None, rid="pipe1", backend=None) -> RepoStore:
    src = src or SRC
    chunks = [c for f, t in src.items() for c in chunk_file(t, f)]
    s = RepoStore(rid, backend)
    s.save(chunks, {"source": "test", "name": "demo"}, dict(src))
    return s


def test_verifier_normalises_short_paths_and_strips_ghosts(tmp_path):
    s = make_store(tmp_path)
    md = "Hashing lives in [core/security.py:1-2]. Ghost [nope.py:1-3] and [app/main.py:900-901]."
    clean, cites, dropped = verify_citations(s, md)
    assert cites[0]["file"] == "app/core/security.py"
    assert "[app/core/security.py:1-2]" in clean
    assert "nope.py" not in clean and "900" not in clean
    assert len(dropped) == 2


def test_import_graph_and_components(tmp_path):
    from app.analysis import analyze, task_signals
    s = make_store(tmp_path)
    a = analyze(s)
    pairs = {(e.src, e.dst) for e in a.edges}
    assert ("app/main.py", "app/routes/users.py") in pairs
    assert ("app/routes/users.py", "app/core/security.py") in pairs
    assert any(f == "app/main.py" for f, _, _ in a.entrypoints)
    kinds = {x["kind"] for x in task_signals(s, a)}
    assert "todo" in kinds


def test_overview_offline_is_grounded(tmp_path):
    from app.agents.overview import build_overview
    s = make_store(tmp_path)
    ov = build_overview(s)
    assert ov["mode"] == "offline" and ov["components"]
    assert all("[" in c["description"] for c in ov["components"])
    assert ov["mermaid"].startswith("flowchart")
    for c in ov["citations"]:
        assert c["file"] in s.files()


def test_living_docs_detect_and_refresh_stale_sections(tmp_path):
    from app.agents.docs import generate_docs, get_docs, refresh_docs
    s = make_store(tmp_path)
    doc = generate_docs(s)
    assert doc["fresh"] and doc["sections"]
    cited = {f for sec in doc["sections"] for f in sec["sources"]}
    assert cited, "docs must cite files so they can track staleness"
    target = sorted(cited)[0]
    src = dict(SRC)
    src[target] = src[target] + "\n# changed\n"
    s2 = make_store(tmp_path, src, backend=s.backend)  # same repo → new snapshot
    s2.meta["file_hashes"] = {}  # force recompute
    from app.store import file_hash
    s2.meta["file_hashes"] = {p: file_hash(t) for p, t in src.items()}
    doc2 = get_docs(s2)
    assert not doc2["fresh"] and any(target in sec["changed_files"] for sec in doc2["sections"])
    doc3 = refresh_docs(s2)
    assert doc3["fresh"]
    assert doc3["changelog"][-1]["event"] == "refreshed"


def test_llm_falls_back_to_next_model_and_logs(monkeypatch, caplog):
    from app.llm import LLMClient, LLMError
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "first")
    monkeypatch.setenv("LLM_FALLBACK_MODELS", "second")
    c = LLMClient()
    calls = []

    def fake(prov, mdl, *a):
        calls.append(mdl)
        if mdl == "first":
            raise LLMError("boom")
        return "ok from second"
    monkeypatch.setattr(c, "_call", fake)
    with caplog.at_level(logging.WARNING):
        assert c.complete("s", "u") == "ok from second"
    assert calls == ["first", "second"]
    assert "FALLBACK model second" in caplog.text


def test_byok_never_uses_fallback_chain(monkeypatch):
    from app.llm import LLMClient, LLMError
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_FALLBACK_MODELS", "second")
    c = LLMClient()
    calls = []

    def fake(prov, mdl, *a):
        calls.append(mdl)
        raise LLMError("bad key")
    monkeypatch.setattr(c, "_call", fake)
    try:
        c.complete("s", "u", api_key="sk-user", model="gpt-x")
    except LLMError:
        pass
    assert calls == ["gpt-x"]


def test_parse_json_tolerates_fences_and_thinking():
    from app.llm import parse_json
    assert parse_json('<think>hmm</think>\n```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Sure! {"b": [1, 2]} hope that helps') == {"b": [1, 2]}


def test_verifier_splits_combined_citations(tmp_path):
    s = make_store(tmp_path)
    clean, cites, dropped = verify_citations(
        s, "See [app/main.py:1-2, 4-5] and [app/main.py:1; app/core/security.py:1-2]. Not [a, b].")
    assert {(c["file"], c["start_line"]) for c in cites} == {
        ("app/main.py", 1), ("app/main.py", 4), ("app/core/security.py", 1)}
    assert "[a, b]" in clean and not dropped


def test_tour_candidates_follow_calls_into_crud():
    """A route that calls `crud.create_user` must bring that definition into the tour."""
    from app.agents.common import follow_calls
    from app.analysis import analyze
    src = {
        "app/__init__.py": "\n",
        "app/routes.py": "from app import crud\n\n\n@router.post('/signup')\ndef register_user(user_in):\n"
                         "    if crud.get_user_by_email(user_in.email):\n        raise ValueError('taken')\n"
                         "    return crud.create_user(user_in)\n",
        "app/crud.py": "def create_user(user_in):\n    return save(hash_password(user_in))\n\n\n"
                       "def get_user_by_email(email):\n    return lookup(email)\n",
    }
    s = make_store(None, src, rid="calls1")
    route = next(c for c in s.chunks if "register_user" in c.text)
    found = follow_calls(s, analyze(s).edges, [route], "what happens when a user signs up")
    names = {c.text.split("(")[0].replace("def ", "") for _, c in found}
    assert {"create_user", "get_user_by_email"} <= names and all(i == 0 for i, _ in found)
