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
    s = RepoStore("demo123")
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


def test_python_chunks_keep_decorators_and_module_code():
    src = '''from fastapi import APIRouter

router = APIRouter()


@router.post("/signup")
def register_user(email: str):
    return email


app_name = "demo"
'''
    chunks = chunk_file(src, "app/users.py")
    handler = next(c for c in chunks if "def register_user" in c.text)
    assert handler.start_line == 6 and '@router.post("/signup")' in handler.text
    covered = {i for c in chunks for i in range(c.start_line, c.end_line + 1)}
    assert all(i in covered for i, ln in enumerate(src.splitlines(), 1) if ln.strip())


def test_public_route_outranks_dev_only_route():
    """A dev-only /private/users seeding route must not beat the real /signup endpoint."""
    files = {
        "backend/app/api/routes/private.py": '''router = APIRouter(prefix="/private")


@router.post("/users/")
def create_user(user_in, session):
    """Create a new user."""
    user = User(email=user_in.email, hashed_password=get_password_hash(user_in.password))
    session.add(user)
    return user
''',
        "backend/app/api/routes/users.py": '''router = APIRouter(prefix="/users")


@router.post("/signup")
def register_user(session, user_in):
    """Create new user without the need to be logged in."""
    return crud.create_user(session=session, user_create=user_in)
''',
    }
    s = RepoStore("rank1")
    s.save([c for f, t in files.items() for c in chunk_file(t, f)], {"source": "test"}, files)
    from app.retrieval import expand_aliases
    top = s.search(expand_aliases("what happens when a user signs up?"), k=3)[0][0]
    assert top.file.endswith("users.py") and "register_user" in top.text
    # …but asking about the private route still finds it
    top = s.search("how does the private users route seed accounts in dev?", k=3)[0][0]
    assert top.file.endswith("private.py")
