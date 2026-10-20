"""Pluggable LLM client — server default (Bedrock Mantle, OpenAI-compatible) + BYOK.

Default model is Kimi K2.5 on Bedrock Mantle; if it errors, the next model in
LLM_FALLBACK_MODELS is tried. Every fallback (next model, offline composer) is
logged so silent degradation is visible in the server log.
"""
import json
import logging
import os
import re

from .config import load_local_env, settings

load_local_env()

log = logging.getLogger(__name__)

DEFAULT_MODEL = "moonshotai.kimi-k2.5"
DEFAULT_FALLBACK_MODELS = "qwen.qwen3-coder-480b-a35b-instruct,deepseek.v3.2"
OPENAI_DEFAULT_BASE = "https://api.openai.com/v1"
GEMINI_OPENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"


class LLMError(RuntimeError):
    pass


class LLMClient:
    """Minimal BYOK interface. Add providers without touching agents."""

    @property
    def provider(self) -> str:
        return os.getenv("LLM_PROVIDER", "none").lower()

    @property
    def model(self) -> str:
        m = os.getenv("LLM_MODEL", "")
        return DEFAULT_MODEL if m in ("", "offline") and self.provider == "openai" else m or "offline"

    @property
    def fallback_models(self) -> list[str]:
        raw = os.getenv("LLM_FALLBACK_MODELS", DEFAULT_FALLBACK_MODELS)
        return [m.strip() for m in raw.split(",") if m.strip() and m.strip() != self.model]

    @property
    def available(self) -> bool:
        p = self.provider
        if p == "openai":
            return bool(os.getenv("OPENAI_API_KEY"))
        if p == "openrouter":
            return bool(os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"))
        if p == "anthropic":
            return bool(os.getenv("ANTHROPIC_API_KEY"))
        if p in ("gemini", "google"):
            return bool(os.getenv("GEMINI_API_KEY"))
        return p == "ollama"

    def can_use(self, override: dict | None) -> bool:
        o = override or {}
        return self.available or bool(o.get("api_key") or o.get("base_url"))

    # ---------- public ----------

    def complete(self, system: str, user: str, *, max_tokens: int = 1500,
                 json_mode: bool = False, provider: str | None = None,
                 model: str | None = None, api_key: str | None = None,
                 base_url: str | None = None) -> str:
        """Return model text or raise LLMError. Server default walks the fallback chain."""
        prov = (provider or self.provider).lower()
        byok = bool(api_key or base_url)
        models = [model or self.model]
        if not byok and not model:
            models += self.fallback_models
        last: Exception | None = None
        for i, m in enumerate(models):
            try:
                out = self._call(prov, m, system, user, max_tokens, json_mode,
                                 api_key, base_url)
                if not out.strip():
                    raise LLMError("empty completion")
                if i:
                    log.warning("llm: FALLBACK model %s answered after %s failed", m, models[0])
                return out.strip()
            except Exception as e:  # noqa: BLE001 — provider SDKs raise many types
                last = e
                log.warning("llm: call failed provider=%s model=%s: %s: %s",
                            prov, m, type(e).__name__, str(e)[:300])
        raise LLMError(f"all models failed: {last}")

    def complete_json(self, system: str, user: str, **kw) -> dict:
        """Complete and parse a JSON object; one repair retry on bad JSON."""
        sys_json = system + "\n\nRespond with ONE valid JSON object only. No prose, no code fences."
        text = self.complete(sys_json, user, json_mode=True, **kw)
        try:
            return parse_json(text)
        except ValueError:
            log.warning("llm: invalid JSON from model; retrying once")
            text = self.complete(sys_json, user + "\n\nYour previous reply was not valid JSON. "
                                 "Return ONLY the JSON object.", json_mode=True, **kw)
            return parse_json(text)

    # ---------- providers ----------

    def _call(self, prov, mdl, system, user, max_tokens, json_mode, api_key, base_url) -> str:
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        if prov in ("openai", "openrouter", "gemini", "google"):
            from openai import OpenAI
            byok = bool(api_key)
            if prov in ("gemini", "google"):
                key = api_key or os.getenv("GEMINI_API_KEY")
                base = base_url or GEMINI_OPENAI_BASE
            else:
                key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")
                # a BYOK key must never be sent to the server's own gateway
                base = base_url or (None if byok else os.getenv("OPENAI_BASE_URL"))
                if prov == "openrouter" and not base:
                    base = "https://openrouter.ai/api/v1"
            if not key:
                raise LLMError(f"no API key for provider {prov}")
            # pin base_url: the SDK otherwise silently reads OPENAI_BASE_URL itself
            client = OpenAI(api_key=key, base_url=base or OPENAI_DEFAULT_BASE,
                            timeout=settings.llm_timeout_seconds, max_retries=1)
            if byok or base_url or prov != "openai" or not os.getenv("OPENAI_PROJECT_ID"):
                client.project = None  # SDK defaults this from OPENAI_PROJECT_ID
            extra: dict = {}
            if prov == "openrouter":
                extra["extra_headers"] = {
                    "HTTP-Referer": os.getenv("SITE_URL", "http://localhost:3000"),
                    "X-Title": "Sherpa AI Mentor"}
            r = client.chat.completions.create(model=mdl, messages=messages,
                                               temperature=0.2, max_tokens=max_tokens, **extra)
            return r.choices[0].message.content or ""
        if prov == "anthropic":
            import anthropic
            key = api_key or os.getenv("ANTHROPIC_API_KEY")
            if not key:
                raise LLMError("no API key for anthropic")
            m = anthropic.Anthropic(api_key=key, timeout=settings.llm_timeout_seconds,
                                      max_retries=1).messages.create(
                model=mdl, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user}])
            return "".join(b.text for b in m.content if getattr(b, "type", "") == "text")
        if prov == "ollama" or base_url:
            import httpx
            base = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
            if base.endswith("/v1"):  # OpenAI-compatible gateway, not native Ollama
                from openai import OpenAI
                client = OpenAI(api_key=api_key or "not-needed", base_url=base,
                                timeout=settings.llm_timeout_seconds, max_retries=1)
                client.project = None
                r = client.chat.completions.create(model=mdl, messages=messages,
                                                   temperature=0.2, max_tokens=max_tokens)
                return r.choices[0].message.content or ""
            r = httpx.post(f"{base}/api/chat", json={
                "model": mdl, "messages": messages, "stream": False,
                **({"format": "json"} if json_mode else {})}, timeout=settings.llm_timeout_seconds)
            r.raise_for_status()
            return r.json().get("message", {}).get("content", "")
        raise LLMError(f"unsupported provider {prov!r}")


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.M)


def parse_json(text: str) -> dict:
    """Lenient JSON parse: strips fences / reasoning, grabs the outermost object."""
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    t = _FENCE.sub("", t).strip()
    try:
        out = json.loads(t)
    except json.JSONDecodeError:
        s, e = t.find("{"), t.rfind("}")
        if s < 0 or e <= s:
            raise ValueError("no JSON object in model output")
        try:
            out = json.loads(t[s:e + 1])
        except json.JSONDecodeError as ex:
            raise ValueError(f"bad JSON: {ex}") from ex
    if not isinstance(out, dict):
        raise ValueError("model JSON is not an object")
    return out


llm = LLMClient()
