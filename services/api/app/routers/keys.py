"""User-owned LLM credentials — BYOK provider keys + any custom endpoint.

Keys are Fernet-encrypted at rest; the API only ever returns `last4`.
`POST /api/keys/test` and `/api/endpoints/test` validate without persisting.
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_session
from ..dbmodels import CustomEndpoint, ProviderKey, User
from ..models import (CustomEndpointCreate, CustomEndpointOut, ProviderKeyCreate,
                      ProviderKeyOut)
from ..security import decrypt_secret, encrypt_secret, get_current_user

router = APIRouter(tags=["credentials"])

PROVIDERS = {"openai", "anthropic", "gemini", "openrouter"}
DEFAULT_MODELS = {"openai": "gpt-4o-mini", "anthropic": "claude-3-5-haiku-latest",
                  "gemini": "gemini-1.5-flash",
                  "openrouter": "openai/gpt-4o-mini"}


def _key_out(k: ProviderKey) -> ProviderKeyOut:
    try:
        last4 = "…" + decrypt_secret(k.key_enc)[-4:]
    except HTTPException:
        last4 = "…????"
    return ProviderKeyOut(id=k.id, label=k.label, provider=k.provider,
                          model=k.model, last4=last4,
                          created_at=str(k.created_at or ""))


# ---------- provider keys ----------

@router.get("/api/keys", response_model=list[ProviderKeyOut])
def list_keys(user: User = Depends(get_current_user),
              db: Session = Depends(get_session)):
    return [_key_out(k) for k in db.query(ProviderKey)
            .filter(ProviderKey.user_id == user.id)
            .order_by(ProviderKey.created_at.desc()).all()]


@router.post("/api/keys", response_model=ProviderKeyOut, status_code=201)
def add_key(body: ProviderKeyCreate, user: User = Depends(get_current_user),
            db: Session = Depends(get_session)):
    provider = body.provider.strip().lower()
    if provider not in PROVIDERS:
        raise HTTPException(422, f"provider must be one of {sorted(PROVIDERS)}")
    key = body.api_key.strip()
    _check_prefix(provider, key)
    k = ProviderKey(user_id=user.id, label=body.label.strip()[:120] or provider,
                    provider=provider,
                    model=body.model.strip() or DEFAULT_MODELS[provider],
                    key_enc=encrypt_secret(key))
    db.add(k)
    db.commit()
    db.refresh(k)
    return _key_out(k)


@router.delete("/api/keys/{key_id}", status_code=204)
def delete_key(key_id: str, user: User = Depends(get_current_user),
               db: Session = Depends(get_session)):
    k = db.query(ProviderKey).filter(ProviderKey.id == key_id,
                                     ProviderKey.user_id == user.id).first()
    if not k:
        raise HTTPException(404, "key not found")
    db.delete(k)
    db.commit()
    return None


def _check_prefix(provider: str, key: str) -> None:
    hints = {"openai": "sk-", "anthropic": "sk-ant-", "gemini": "AI",
             "openrouter": "sk-or-"}
    if not key.startswith(hints[provider]):
        raise HTTPException(422, f"that doesn't look like an {provider} key "
                                 f"(expected to start with {hints[provider]!r})")


# ---------- custom endpoints ----------

@router.get("/api/endpoints", response_model=list[CustomEndpointOut])
def list_endpoints(user: User = Depends(get_current_user),
                   db: Session = Depends(get_session)):
    return [_ep_out(e) for e in db.query(CustomEndpoint)
            .filter(CustomEndpoint.user_id == user.id)
            .order_by(CustomEndpoint.created_at.desc()).all()]


def _ep_out(e: CustomEndpoint) -> CustomEndpointOut:
    return CustomEndpointOut(id=e.id, name=e.name, base_url=e.base_url,
                             kind=e.kind, model=e.model,
                             has_key=bool(e.api_key_enc),
                             created_at=str(e.created_at or ""))


@router.post("/api/endpoints", response_model=CustomEndpointOut, status_code=201)
def add_endpoint(body: CustomEndpointCreate,
                 user: User = Depends(get_current_user),
                 db: Session = Depends(get_session)):
    url = body.base_url.strip().rstrip("/")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(422, "base_url must start with http(s)://")
    if body.kind not in ("openai-compatible", "ollama"):
        raise HTTPException(422, "kind must be openai-compatible or ollama")
    e = CustomEndpoint(user_id=user.id, name=body.name.strip()[:120] or url,
                       base_url=url, kind=body.kind,
                       model=body.model.strip() or "default",
                       api_key_enc=encrypt_secret(body.api_key.strip())
                       if body.api_key.strip() else "")
    db.add(e)
    db.commit()
    db.refresh(e)
    return _ep_out(e)


@router.delete("/api/endpoints/{endpoint_id}", status_code=204)
def delete_endpoint(endpoint_id: str, user: User = Depends(get_current_user),
                    db: Session = Depends(get_session)):
    e = db.query(CustomEndpoint).filter(CustomEndpoint.id == endpoint_id,
                                        CustomEndpoint.user_id == user.id).first()
    if not e:
        raise HTTPException(404, "endpoint not found")
    db.delete(e)
    db.commit()
    return None


@router.post("/api/endpoints/test")
def test_endpoint(body: CustomEndpointCreate,
                  user: User = Depends(get_current_user)):
    """Ping any endpoint before saving — returns reachability, stores nothing."""
    url = body.base_url.strip().rstrip("/")
    probe = f"{url}/models" if body.kind == "openai-compatible" else f"{url}/api/tags"
    headers = {"Authorization": f"Bearer {body.api_key}"} if body.api_key else {}
    try:
        r = httpx.get(probe, headers=headers, timeout=8)
        return {"ok": r.status_code < 500, "status": r.status_code,
                "hint": "reachable" if r.status_code < 500 else "server errored"}
    except httpx.ConnectError:
        return {"ok": False, "status": None, "hint": "connection refused — check host/port"}
    except httpx.TimeoutException:
        return {"ok": False, "status": None, "hint": "timed out after 8s"}
    except Exception as ex:  # never leak internals
        return {"ok": False, "status": None, "hint": f"unreachable ({type(ex).__name__})"}
