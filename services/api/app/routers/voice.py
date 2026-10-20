"""Spoken explanations with Amazon Polly.

`POST /api/voice/speak` turns plain text into MP3. Credentials come from
POLLY_ACCESS_KEY_ID / POLLY_SECRET_ACCESS_KEY when set, otherwise boto3's usual chain
(env vars, ~/.aws profile, instance role); the Bedrock API key cannot sign Polly calls.
When Polly is unavailable the endpoint answers 503 and the web app falls back to the
browser's own speech, so voice keeps working without AWS.
"""
import hashlib
import logging
import threading
import time
from collections import OrderedDict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..config import settings
from ..dbmodels import User
from ..guards import enforce
from ..security import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(tags=["voice"])

MAX_CHARS = 3000          # Polly's SynthesizeSpeech limit for plain text
CACHE_ITEMS = 256         # replaying a tour step shouldn't cost another call
AUTH_RETRY_AFTER = 300    # after bad credentials, stop calling AWS for a while

_client = None
_lock = threading.Lock()
_cache: "OrderedDict[str, bytes]" = OrderedDict()
_down_until = 0.0


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_CHARS)


def polly():
    """A Polly client, or None when there are no AWS credentials at all."""
    global _client
    with _lock:
        if _client is None:
            import boto3

            kw = {"region_name": settings.polly_region or settings.aws_default_region}
            if settings.polly_access_key_id and settings.polly_secret_access_key:
                kw |= {"aws_access_key_id": settings.polly_access_key_id,
                       "aws_secret_access_key": settings.polly_secret_access_key}
            session = boto3.Session()
            if "aws_access_key_id" not in kw and session.get_credentials() is None:
                return None
            _client = session.client("polly", **kw)
        return _client


def available() -> bool:
    return settings.polly_enabled and time.time() >= _down_until and polly() is not None


def synthesize(text: str) -> bytes:
    """MP3 for `text`. Tries the configured engine, then neural if that voice lacks it."""
    global _down_until
    from botocore.exceptions import BotoCoreError, ClientError

    key = hashlib.sha256(f"{settings.polly_voice}|{settings.polly_engine}|{text}".encode()).hexdigest()
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]

    client = polly()
    if client is None:
        raise HTTPException(503, "voice is not configured")
    engines = [settings.polly_engine] + (["neural"] if settings.polly_engine != "neural" else [])
    for engine in engines:
        try:
            r = client.synthesize_speech(Text=text, TextType="text", OutputFormat="mp3",
                                         VoiceId=settings.polly_voice, Engine=engine)
            audio = r["AudioStream"].read()
            break
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in {"UnrecognizedClientException", "InvalidClientTokenId", "AccessDeniedException",
                        "InvalidSignatureException", "ExpiredTokenException"}:
                _down_until = time.time() + AUTH_RETRY_AFTER
                log.warning("polly: credentials rejected (%s); using browser speech for %ss", code, AUTH_RETRY_AFTER)
                raise HTTPException(503, "voice is not available") from e
            if code == "ValidationException" and engine != engines[-1]:
                log.info("polly: %s does not support %s, trying neural", settings.polly_voice, engine)
                continue
            log.warning("polly: %s", code or e)
            raise HTTPException(502, "could not synthesize speech") from e
        except BotoCoreError as e:
            log.warning("polly: %s", e)
            raise HTTPException(502, "could not synthesize speech") from e

    with _lock:
        _cache[key] = audio
        while len(_cache) > CACHE_ITEMS:
            _cache.popitem(last=False)
    return audio


@router.get("/api/voice/config")
def voice_config(user: User = Depends(get_current_user)):
    ok = available()
    return {"provider": "polly" if ok else "browser",
            "voice": settings.polly_voice if ok else None,
            "max_chars": MAX_CHARS}


@router.post("/api/voice/speak")
def speak(body: SpeakRequest, request: Request, user: User = Depends(get_current_user)):
    enforce(request, "voice", 150, 60, who=str(user.id))  # answers arrive a sentence at a time
    if not available():
        raise HTTPException(503, "voice is not available")
    audio = synthesize(body.text.strip())
    return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=3600"})
