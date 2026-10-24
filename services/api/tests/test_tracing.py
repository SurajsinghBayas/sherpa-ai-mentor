"""Traces carry sizes, models and token counts, never code, prompts or keys."""
from types import SimpleNamespace

from app import tracing


def test_inputs_hide_content_and_keys(monkeypatch):
    monkeypatch.delenv("LANGSMITH_LOG_CONTENT", raising=False)
    out = tracing._inputs({"self": object(), "store": SimpleNamespace(repo_id="r1"),
                           "question": "SECRET_CODE", "api_key": "sk-x", "k": 10})
    assert out == {"repo_id": "r1", "question": "<str 11 chars>", "k": 10}


def test_outputs_hide_content(monkeypatch):
    monkeypatch.delenv("LANGSMITH_LOG_CONTENT", raising=False)
    assert tracing._outputs("an answer quoting code") == {"output": "<str 22 chars>"}


def test_traced_is_a_noop_when_off(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    f = lambda: 1  # noqa: E731
    assert tracing.traced("x")(f) is f
