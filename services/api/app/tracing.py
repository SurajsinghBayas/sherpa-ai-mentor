"""LangSmith tracing: timing of agent steps, plus model, tokens and cost of every LLM call.

Off unless LANGSMITH_TRACING=true and LANGSMITH_API_KEY are set. Traces carry metadata only
(sizes, model, token counts); prompts, code and answers are sent only with
LANGSMITH_LOG_CONTENT=true, since private-mode code must not leave the server. Cost comes from
token counts and the model prices configured in LangSmith (Settings → Model pricing).
"""
import functools
import logging
import os

log = logging.getLogger(__name__)


def enabled() -> bool:
    return os.getenv("LANGSMITH_TRACING", "").lower() == "true" and bool(os.getenv("LANGSMITH_API_KEY"))


def _log_content() -> bool:
    return os.getenv("LANGSMITH_LOG_CONTENT", "").lower() == "true"


def _shape(value):
    """What a value looks like without what it says."""
    if isinstance(value, str):
        return f"<str {len(value)} chars>"
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return f"<{type(value).__name__} {len(value)}>"
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in list(value.items())[:20]
                if not any(s in k.lower() for s in ("key", "token", "secret", "password"))}
    return f"<{type(value).__name__}>"


def _inputs(inputs: dict) -> dict:
    out = {}
    for k, v in inputs.items():
        if k in ("self", "api_key", "llm_override", "base_url", "system", "user"):
            continue
        if k == "store":
            out["repo_id"] = getattr(v, "repo_id", None)
            continue
        if k in ("prov", "mdl"):  # names, not content
            out["provider" if k == "prov" else "model"] = v
            continue
        out[k] = v if _log_content() and isinstance(v, (str, int, float, bool)) else _shape(v)
    return out


def _outputs(outputs) -> dict:
    out = outputs if _log_content() and isinstance(outputs, dict) else _shape(outputs)
    return out if isinstance(out, dict) else {"output": out}


def _run():
    if not enabled():
        return None
    try:
        from langsmith.run_helpers import get_current_run_tree
        return get_current_run_tree()
    except Exception:  # noqa: BLE001 — tracing must never break a request
        return None


def record_usage(usage) -> None:
    """Token counts of the model reply, on the current llm run; LangSmith prices them."""
    rt = _run()
    if usage is None or rt is None:
        return
    get = (lambda k: usage.get(k)) if isinstance(usage, dict) else (lambda k: getattr(usage, k, None))
    inp = get("prompt_tokens") or get("input_tokens") or 0
    outp = get("completion_tokens") or get("output_tokens") or 0
    rt.set(usage_metadata={"input_tokens": inp, "output_tokens": outp, "total_tokens": inp + outp})


def traced(name: str, run_type: str = "chain"):
    """Time a function as a LangSmith run; a no-op when tracing is off or langsmith is missing."""
    def wrap(fn):
        if not enabled():
            return fn
        try:
            from langsmith import traceable
        except ImportError:
            log.warning("tracing: LANGSMITH_TRACING is on but langsmith isn't installed")
            return fn
        inner = traceable(name=name, run_type=run_type, process_inputs=_inputs,
                          process_outputs=_outputs)(fn)
        return functools.wraps(fn)(inner)
    return wrap


def tag_model(provider: str, model: str) -> None:
    """Names the model on the current llm run so LangSmith can price it."""
    rt = _run()
    if rt is not None:
        rt.metadata.update({"ls_provider": provider, "ls_model_name": model})
