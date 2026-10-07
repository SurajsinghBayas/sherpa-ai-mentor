"""Grounding tests — the core IM-05 promise. Must pass in CI."""
from app.chunk import chunk_file
from app.store import RepoStore


def _demo_store(tmp_path) -> RepoStore:
    src = '''from fastapi import FastAPI

app = FastAPI()

@app.post("/signup")
def signup(email: str, password: str):
    """Create a user account."""
    user = create_user(email, password)
    return {"id": user.id}


def create_user(email, password):
    return save_to_db(email)
'''
    chunks = chunk_file(src, "app/auth.py")
    s = RepoStore(str(tmp_path), "demo123")
    s.save(chunks, {"source": "test"})
    return s


def test_chunk_preserves_provenance(tmp_path):
    s = _demo_store(tmp_path)
    assert all(c.start_line >= 1 and c.end_line >= c.start_line for c in s.chunks)
    assert "app/auth.py" in s.files()


def test_search_finds_signup(tmp_path):
    s = _demo_store(tmp_path)
    hits = s.search("how does user signup work?", k=3)
    assert hits, "expected at least one hit"
    assert any("auth.py" in c.file for c, _ in hits)


def test_citation_verifier_rejects_ghosts(tmp_path):
    from app.agents.mentor import verify_citations
    s = _demo_store(tmp_path)
    md = "Signup lives in [app/auth.py:5-9] and nowhere in [nope/missing.py:1-5]."
    _, cites, dropped = verify_citations(s, md)
    assert any(c["file"] == "app/auth.py" for c in cites)
    assert dropped == ["[nope/missing.py:1-5]"]


def test_answer_is_grounded(tmp_path):
    from app.agents.mentor import answer_question
    s = _demo_store(tmp_path)
    out = answer_question(s, "How does user signup work?")
    assert out["citations"], "answer must carry citations"
    for c in out["citations"]:
        assert c["file"] in s.files()


def test_tour_and_tasks(tmp_path):
    from app.agents.mentor import build_tour, suggest_starter_tasks
    s = _demo_store(tmp_path)
    tour = build_tour(s, "user signup")
    assert tour["steps"], "tour must have steps"
    tasks = suggest_starter_tasks(s)
    assert tasks["tasks"], "must suggest starter tasks"
