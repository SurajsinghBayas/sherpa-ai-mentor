"""Repo City (history parsing, buildings, timeline) and the skill check (questions, blind check, grading)."""
from app import history
from app.agents import city as city_mod
from app.agents import quiz as qz
from app.chunk import chunk_file
from app.store import RepoStore

SRC = {
    "app/main.py": "from app.routes import users\n\n\ndef create_app():\n    return users.router\n",
    "app/routes/users.py": "from app.core.security import hash_password\n\n\ndef signup_user(email, pw):\n"
                           "    return hash_password(pw)\n\n\ndef delete_account(uid):\n    return uid\n",
    "app/core/security.py": "def hash_password(p):\n    return 'x' + p\n\n\ndef verify_password(p, h):\n"
                            "    return hash_password(p) == h\n",
    "app/core/config.py": "class Settings:\n    database_url = ''\n\n\ndef load_settings():\n    return Settings()\n",
    "app/db/models.py": "class UserRecord:\n    pass\n\n\nclass SessionRecord:\n    pass\n",
    "web/src/api.ts": "export function fetchUsers() {\n  return fetch('/users')\n}\n",
    "web/src/App.tsx": "import { fetchUsers } from './api'\nexport function App() {\n  return fetchUsers()\n}\n",
    "README.md": "# Demo\n\nA demo service.\n",
}

LOG = (
    "\x1eaaa1\x1f1700000300\x1fAdd signup\nA\tapp/routes/users.py\nM\tapp/main.py\n"
    "\x1eaaa0\x1f1700000000\x1fInitial commit\nA\tapp/main.py\nA\tapp/core/security.py\nA\tREADME.md\n"
)


def store(src=SRC, rid="cityq") -> RepoStore:
    s = RepoStore(rid)
    s.save([c for f, t in src.items() for c in chunk_file(t, f)],
           {"source": "https://github.com/x/y", "kind": "git", "name": "x/y", "commit": "c1"}, dict(src))
    return s


def test_history_parse_oldest_first():
    commits = history._parse(LOG)
    assert [c["subject"] for c in commits] == ["Initial commit", "Add signup"]
    assert commits[1]["files"] == [["A", "app/routes/users.py"], ["M", "app/main.py"]]


def test_city_buildings_districts_and_timeline(monkeypatch):
    monkeypatch.setattr(city_mod, "fetch_history", lambda meta: {"commits": history._parse(LOG), "truncated": False})
    c = city_mod.build_city(store())
    paths = [b["path"] for b in c["buildings"]]
    assert set(paths) == set(SRC)  # code files and docs/config
    assert c["districts"][-1]["name"] == "Docs & config" and not c["districts"][-1]["code"]
    b = {x["path"]: x for x in c["buildings"]}
    assert b["app/main.py"]["changes"] == 2 and b["app/routes/users.py"]["born"] == 1
    assert b["app/core/config.py"]["born"] == 0 and b["app/core/config.py"]["changes"] == 0  # older than the window
    assert [f["subject"] for f in c["timeline"]] == ["Initial commit", "Add signup"]
    idx = {p: i for i, p in enumerate(paths)}
    assert [idx["app/routes/users.py"], idx["app/core/security.py"]] in c["edges"]
    assert c["history"] == "full"


def test_city_without_history(monkeypatch):
    monkeypatch.setattr(city_mod, "fetch_history", lambda meta: None)
    c = city_mod.build_city(store(rid="nohist"))
    assert c["timeline"] == [] and c["history"] == "none" and c["buildings"]


def test_offline_quiz_hides_answers_and_grades():
    s = store(rid="quiz1")
    pub = qz.build_quiz(s)  # tests have no model: questions come from static analysis
    assert pub["mode"] == "offline" and 3 <= len(pub["questions"]) <= qz.QUESTIONS
    for q in pub["questions"]:
        assert len(q["options"]) == 4 and "answer" not in q and "explanation" not in q
    full = s.cache_get("quiz")["quizzes"][pub["id"]]
    right = [q["answer"] for q in full["questions"]]
    r = qz.grade(s, pub["id"], right)
    assert r["correct"] == r["total"] == len(right) and r["level"] == "Ready to contribute"
    assert all(x["cite"]["file"] in SRC for x in r["results"])  # every answer is backed by real code
    wrong = [(a + 1) % 4 for a in right]
    r2 = qz.grade(s, pub["id"], wrong)
    assert r2["correct"] == 0 and r2["level"] == "Keep exploring" and r2["weak"]
    assert qz.grade(s, "nope", right) is None
    assert qz.build_quiz(s)["id"] == pub["id"]  # the same quiz until a retake
    assert qz.build_quiz(s, fresh=True)["id"] != pub["id"]


def test_model_quiz_keeps_only_cited_questions_the_blind_check_agrees_with(monkeypatch):
    s = store(rid="quiz2")
    monkeypatch.setattr(qz.llm, "can_use", lambda override=None: True)
    written = {"questions": [
        {"area": "app", "difficulty": "easy", "question": "Which function hashes passwords?",
         "options": ["hash_password", "verify_password", "signup_user", "load_settings"], "answer": 0,
         "explanation": "It is defined here [app/core/security.py:1-2]."},
        {"area": "app", "difficulty": "hard", "question": "What does signup_user return?",
         "options": ["The hashed password", "A user id", "Nothing", "A token"], "answer": 0,
         "explanation": "It returns the hash [app/routes/users.py:4-5]."},
        {"area": "app", "difficulty": "medium", "question": "Which file has no proof?",
         "options": ["a", "b", "c", "d"], "answer": 1, "explanation": "Made up [nope.py:1-2]."},
        {"area": "app", "difficulty": "easy", "question": "Bad options?",
         "options": ["x", "x", "y", "z"], "answer": 0, "explanation": "[app/main.py:1-2]"},
    ]}
    calls = []

    def fake(system, prompt, **kw):
        calls.append(prompt)
        if len(calls) == 1:
            return written
        return {"answers": [{"n": 1, "choice": "A"}, {"n": 2, "choice": "B"}]}  # disagrees on question 2

    monkeypatch.setattr(qz.llm, "complete_json", fake)
    pub = qz.build_quiz(s)
    assert pub["mode"] == "llm" and pub["checked"]
    texts = [q["question"] for q in pub["questions"]]
    assert "Which function hashes passwords?" in texts
    assert "What does signup_user return?" not in texts  # the blind check got a different answer
    assert "Which file has no proof?" not in texts and "Bad options?" not in texts
    assert "CODE app/core/security.py:1-" in calls[1] and "def hash_password" in calls[1]  # it saw the cited code
    full = s.cache_get("quiz")["quizzes"][pub["id"]]
    q = next(x for x in full["questions"] if x["question"] == "Which function hashes passwords?")
    assert q["options"][q["answer"]] == "hash_password"  # still right after the options were shuffled


def test_quiz_endpoints(client):
    r = client.post("/api/auth/register", json={"name": "Q", "email": "q@example.com", "password": "pw-123456789"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.post("/api/quiz", json={"repo_id": "missing1"}, headers=h).status_code == 404
    assert client.get("/api/quiz/attempts?repo_id=missing1", headers=h).status_code == 404
    assert client.post("/api/city", json={"repo_id": "missing1"}).status_code == 401
