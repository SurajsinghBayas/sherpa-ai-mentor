"""Voice input: spoken code names are fixed, and the listen socket streams utterances.

A fake Transcribe stands in for AWS, so no audio leaves the test."""
import json

import pytest
from starlette.websockets import WebSocketDisconnect

from app.chunk import Chunk
from app.spoken import correct, vocabulary
from app.store import RepoStore

VOCAB = {"getcurrentuser": "get_current_user", "depspy": "deps.py", "fastapi": "FastAPI",
         "tanstack": "TanStack", "createaccesstoken": "create_access_token"}


@pytest.mark.parametrize("heard, fixed", [
    ("What does get current user in deps dot py do?", "What does get_current_user in deps.py do?"),
    ("Where is the token created in the fast API back end?", "Where is the token created in the FastAPI back end?"),
    ("Does it use tan stack query?", "Does it use TanStack query?"),
    ("How does create access token work?", "How does create_access_token work?"),
    ("How do I run the tests and see the results?", "How do I run the tests and see the results?"),
])
def test_spoken_names_become_the_repos_names(heard, fixed):
    assert correct(heard, VOCAB) == fixed


def test_vocabulary_comes_from_the_repo_only():
    store = RepoStore("vocab-test")
    store.save([Chunk(file="backend/app/api/deps.py", start_line=1, end_line=3,
                      text="from fastapi import Depends\n\ndef get_current_user(token):\n    return token\n")],
               {"name": "t"}, {"backend/app/api/deps.py": "def get_current_user(token): ..."})
    v = vocabulary(store)
    assert v["getcurrentuser"] == "get_current_user" and v["depspy"] == "deps.py"
    assert v["fastapi"] == "FastAPI"
    assert "return" not in v.values() and "token" not in v.values()  # plain words stay out


class FakeUtterance:
    """Stands in for app.stt.Utterance: 'hears' whatever text the test queued."""
    script = ["get current user in deps dot py"]
    opened = 0

    def __init__(self, on_partial):
        self.on_partial, self.audio, self.error = on_partial, b"", None

    async def open(self):
        FakeUtterance.opened += 1

    async def feed(self, pcm):
        self.audio += pcm
        await self.on_partial(self.script[0].split(" in ")[0])

    async def finish(self):
        return self.script[0] if self.audio else ""

    async def cancel(self):
        pass


@pytest.fixture()
def listening(client, monkeypatch, tmp_path):
    from app import stt
    from app.config import settings
    monkeypatch.setattr(stt, "available", lambda: True)
    monkeypatch.setattr(stt, "Utterance", FakeUtterance)
    monkeypatch.setattr(settings, "allow_local_ingest", True)
    r = client.post("/api/auth/register", json={"email": "ears@example.com", "password": "password123"})
    token = r.json()["access_token"]
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "deps.py").write_text("def get_current_user(token):\n    return token\n")
    rid = client.post("/api/ingest", json={"local_path": str(repo)},
                      headers={"Authorization": f"Bearer {token}"}).json()["repo_id"]
    return token, rid


def test_listen_streams_an_utterance_and_fixes_names(client, listening):
    token, rid = listening
    with client.websocket_connect("/api/voice/listen", headers={"origin": "http://localhost:3000"}) as ws:
        ws.send_text(json.dumps({"token": token, "repo_id": rid}))
        assert ws.receive_json()["type"] == "ready"
        ws.send_text(json.dumps({"type": "start"}))
        ws.send_bytes(b"\x00\x01" * 512)
        partial = ws.receive_json()
        assert partial == {"type": "partial", "id": 1, "text": "get_current_user"}
        ws.send_text(json.dumps({"type": "end"}))
        final = ws.receive_json()
        assert final["type"] == "final" and final["id"] == 1
        assert final["text"] == "get_current_user in deps.py"
        assert final["heard"] == "get current user in deps dot py"


def test_a_cancelled_utterance_sends_nothing(client, listening):
    token, rid = listening
    with client.websocket_connect("/api/voice/listen") as ws:
        ws.send_text(json.dumps({"token": token, "repo_id": rid}))
        ws.receive_json()
        ws.send_text(json.dumps({"type": "start"}))
        ws.send_text(json.dumps({"type": "cancel"}))
        ws.send_text(json.dumps({"type": "start"}))
        ws.send_bytes(b"\x00\x01" * 512)
        assert ws.receive_json()["id"] == 2  # the next utterance is numbered on; nothing for 1


@pytest.mark.parametrize("hello, origin", [
    ({"token": "not-a-jwt"}, "http://localhost:3000"),
    (None, "https://evil.example"),
])
def test_listen_rejects_bad_tokens_and_foreign_sites(client, listening, hello, origin):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/voice/listen", headers={"origin": origin}) as ws:
            if hello:
                ws.send_text(json.dumps(hello))
            ws.receive_json()


def test_listen_says_when_transcribe_is_off(client, listening, monkeypatch):
    from app import stt
    monkeypatch.setattr(stt, "available", lambda: False)
    token, _ = listening
    with client.websocket_connect("/api/voice/listen") as ws:
        ws.send_text(json.dumps({"token": token}))
        assert ws.receive_json()["type"] == "error"
    assert client.get("/api/voice/config", headers={"Authorization": f"Bearer {token}"}).json()["stt"] == "browser"


def test_spoken_questions_are_fixed_before_answering(client, listening):
    token, rid = listening
    r = client.post("/api/ask", json={"repo_id": rid, "question": "what does get current user do",
                                      "spoken": True}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and "get_current_user" in r.json()["answer_markdown"]
