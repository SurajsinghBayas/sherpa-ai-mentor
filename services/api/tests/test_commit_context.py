"""Ask Sherpa with commit history: picking related commits, citing them, and dropping made-up ids."""
from app import history
from app.agents import commits as cm
from app.agents import mentor
from app.chunk import chunk_file
from app.store import RepoStore

SRC = {
    "app/auth.py": "def signup_user(email, pw):\n    return hash_password(pw)\n\n\ndef login_user(email, pw):\n    return True\n",
    "app/db.py": "def connect():\n    return 'db'\n",
}
A, B, C = "a1b2c3d4e5f60718", "b2c3d4e5f6071829", "c3d4e5f60718293a"
LOG = (f"\x1e{C}\x1f1760000600\x1fRiya\x1fAdd login rate limit\nM\tapp/auth.py\n"
       f"\x1e{B}\x1f1760000300\x1fDev\x1fSwitch database driver\nM\tapp/db.py\n"
       f"\x1e{A}\x1f1760000000\x1fRiya\x1fAdd signup flow\nA\tapp/auth.py\nA\tapp/db.py\n")


def store(rid):
    s = RepoStore(rid)
    s.save([c for f, t in SRC.items() for c in chunk_file(t, f)],
           {"source": "https://github.com/acme/shop", "kind": "git", "name": "acme/shop", "commit": "c1"}, dict(SRC))
    return s


def fake_history(monkeypatch, calls=None):
    def fetch(meta):
        if calls is not None:
            calls.append(meta["name"])
        return {"commits": history._parse(LOG), "truncated": False}
    monkeypatch.setattr(history, "fetch_history", fetch)


def test_parse_keeps_authors_and_old_logs_still_parse():
    c = history._parse(LOG)
    assert [x["author"] for x in c] == ["Riya", "Dev", "Riya"] and c[-1]["subject"] == "Add login rate limit"
    assert history._parse("\x1eabc\x1f17\x1fOld style\nM\ta.py\n")[0]["author"] == ""


def test_relevant_commits_and_verification():
    h = {"commits": history._parse(LOG), "truncated": False}
    picked = cm.relevant(h, "when was the login rate limit added?", ["app/auth.py"])
    assert picked[0]["subject"] == "Add login rate limit"  # newest first
    assert "Switch database driver" in [c["subject"] for c in picked]  # one of the newest few
    block = cm.format_commits(h, picked)
    assert '[commit c3d4e5f] 2025-10-09, by Riya: "Add login rate limit"' in block
    text, used, dropped = cm.verify_commits(f"Added later [commit {C}] and [commit deadbeef1].", h,
                                            {"source": "https://github.com/acme/shop", "kind": "git"})
    assert text == "Added later [commit c3d4e5f] and."
    assert used[0]["url"] == f"https://github.com/acme/shop/commit/{C[:10]}" and used[0]["author"] == "Riya"
    assert dropped == ["commit deadbeef1"]
    grouped, used2, _ = cm.verify_commits(f"Both [commit {A[:7]}, commit {B[:7]}] and [commits {C[:7]}, {A[:7]}].", h, {})
    assert grouped == f"Both [commit {A[:7]}] [commit {B[:7]}] and [commit {C[:7]}] [commit {A[:7]}]."
    assert len(used2) == 3 and used2[0]["url"] == ""
    assert cm.asks_history("Who changed the login flow?") and not cm.asks_history("How does hashing work?")


def test_offline_answer_lists_related_commits(monkeypatch):
    fake_history(monkeypatch)
    r = mentor.answer_question(store("hist1"), "When was signup added?")
    shorts = [c["short"] for c in r["commits"]]
    assert A[:7] in shorts and r["verify"]["grounded"]
    assert f"[commit {A[:7]}]" in r["answer_markdown"]


def test_model_sees_commits_and_fake_ids_are_removed(monkeypatch):
    fake_history(monkeypatch)
    prompts = []
    monkeypatch.setattr(mentor.llm, "can_use", lambda override=None: True)

    def complete(system, prompt, **kw):
        prompts.append(prompt)
        return (f"Riya added the rate limit on 2025-10-09 [commit {C[:7]}]. It lives in `login_user` "
                "[app/auth.py:5-6]. It was reviewed in [commit 0badc0de].")
    monkeypatch.setattr(mentor.llm, "complete", complete)
    r = mentor.answer_question(store("hist2"), "Who added the login rate limit and when?")
    assert "Commit history, newest first" in prompts[0] and "Add login rate limit" in prompts[0]
    assert "[commit 0badc0de]" not in r["answer_markdown"] and r["verify"]["unchecked_claims"] == ["commit 0badc0de"]
    assert [c["short"] for c in r["commits"]] == [C[:7]]


def test_ordinary_questions_never_fetch_history(monkeypatch):
    calls = []
    fake_history(monkeypatch, calls)
    s = store("hist3")
    r = mentor.answer_question(s, "How does password hashing work?")
    assert calls == [] and r["commits"] == []
    mentor.answer_question(s, "What changed recently?")
    mentor.answer_question(s, "Who wrote the db code?")
    assert calls == ["acme/shop"]  # fetched once, then cached for this indexed commit


def test_file_facts_and_whole_word_matching():
    h = {"commits": history._parse(LOG), "truncated": False}
    facts = cm.file_facts(h, ["app/auth.py", "app/missing.py"])
    assert facts[0] == ("- app/auth.py: last changed 2025-10-09 by Riya [commit c3d4e5f]; 2 commit(s) touch it; "
                        "added 2025-10-09 by Riya [commit a1b2c3d]")
    assert facts[1] == "- app/missing.py: not changed in the fetched history"
    assert cm.named_files("who changed auth.py?", list(SRC), ["app/db.py"]) == ["app/auth.py", "app/db.py"]
    old = [{"sha": "d" * 10, "t": 1, "author": "bot", "subject": "bump langgraph", "files": [["M", "uv.lock"]]},
           {"sha": "e" * 10, "t": 2, "author": "Ana", "subject": "fix graph edges", "files": [["M", "x.py"]]}]
    newer = [{"sha": f"{i}" * 10, "t": 10 + i, "author": "Ana", "subject": "docs", "files": []} for i in range(4)]
    picked = cm.relevant({"commits": old + newer}, "how is the graph built", [], n=6)
    assert "fix graph edges" in [c["subject"] for c in picked] and "bump langgraph" not in [c["subject"] for c in picked]
