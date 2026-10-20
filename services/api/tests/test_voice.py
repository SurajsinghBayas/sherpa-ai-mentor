"""Spoken explanations via Amazon Polly — a fake client stands in for AWS."""
import io

import pytest
from botocore.exceptions import ClientError


def _auth(client, email="voice@example.com"):
    r = client.post("/api/auth/register", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class FakePolly:
    def __init__(self, fail_engine=None, error=None):
        self.calls, self.fail_engine, self.error = [], fail_engine, error

    def synthesize_speech(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise ClientError({"Error": {"Code": self.error}}, "SynthesizeSpeech")
        if kw["Engine"] == self.fail_engine:
            raise ClientError({"Error": {"Code": "ValidationException"}}, "SynthesizeSpeech")
        return {"AudioStream": io.BytesIO(b"ID3-mp3-" + kw["Engine"].encode())}


@pytest.fixture()
def fake(monkeypatch):
    import app.routers.voice as v
    f = FakePolly()
    monkeypatch.setattr(v, "_client", f)
    monkeypatch.setattr(v, "_down_until", 0.0)
    v._cache.clear()
    return f


def test_speak_returns_mp3_and_caches(client, fake):
    h = _auth(client)
    assert client.get("/api/voice/config", headers=h).json()["provider"] == "polly"
    for _ in range(2):
        r = client.post("/api/voice/speak", json={"text": "The router calls the service."}, headers=h)
        assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
    assert r.content.startswith(b"ID3") and len(fake.calls) == 1


def test_falls_back_to_neural_when_voice_lacks_engine(client, fake, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "polly_engine", "generative")
    fake.fail_engine = "generative"
    r = client.post("/api/voice/speak", json={"text": "hello"}, headers=_auth(client))
    assert r.status_code == 200 and r.content.endswith(b"neural")
    assert [c["Engine"] for c in fake.calls] == ["generative", "neural"]


def test_bad_credentials_switch_to_browser_voice(client, fake):
    fake.error = "UnrecognizedClientException"
    h = _auth(client)
    assert client.post("/api/voice/speak", json={"text": "hello"}, headers=h).status_code == 503
    assert client.get("/api/voice/config", headers=h).json()["provider"] == "browser"


def test_speak_needs_auth_and_bounded_text(client, fake):
    assert client.post("/api/voice/speak", json={"text": "hi"}).status_code == 401
    r = client.post("/api/voice/speak", json={"text": "x" * 3001}, headers=_auth(client))
    assert r.status_code == 422 and not fake.calls


def test_spoken_answers_use_conversational_format():
    from app.agents.mentor import _llm_prompt
    spoken = _llm_prompt("How does login work?", "ctx", "map", [], spoken=True)
    written = _llm_prompt("How does login work?", "ctx", "map", [])
    assert "read aloud" in spoken and "How it works" not in spoken
    assert "How it works" in written and "CITATIONS" in spoken
