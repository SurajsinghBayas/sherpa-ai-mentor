"""Voice: Amazon Polly speaks, Amazon Transcribe listens.

`POST /api/voice/speak` turns plain text into MP3. `WS /api/voice/listen` turns the user's
speech into text (see app/stt.py), fixing code names with the repo's vocabulary (app/spoken.py). Credentials come from
POLLY_ACCESS_KEY_ID / POLLY_SECRET_ACCESS_KEY when set, otherwise boto3's usual chain
(env vars, ~/.aws profile, instance role); the Bedrock API key cannot sign Polly calls.
When Polly is unavailable the endpoint answers 503 and the web app falls back to the
browser's own speech, so voice keeps working without AWS.
"""
import asyncio
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .. import db as dbmod
from .. import stt
from ..config import settings
from ..dbmodels import User
from ..guards import enforce
from ..security import _user_from_token, get_current_user
from ..spoken import correct, vocabulary

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
            "max_chars": MAX_CHARS,
            "stt": "transcribe" if stt.available() else "browser"}


@router.post("/api/voice/speak")
def speak(body: SpeakRequest, request: Request, user: User = Depends(get_current_user)):
    enforce(request, "voice", 150, 60, who=str(user.id))  # answers arrive a sentence at a time
    if not available():
        raise HTTPException(503, "voice is not available")
    audio = synthesize(body.text.strip())
    return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=3600"})


# ── listening: WS /api/voice/listen ──────────────────────────────────────────
#
# One socket per voice conversation. The browser sends, as text frames:
#   {"token": jwt, "repo_id": "..."}   first, to sign in (browsers can't set headers on sockets)
#   {"type": "start"} … binary PCM16 16 kHz mono … {"type": "end"}   for each utterance
#   {"type": "cancel"}                  drop the current utterance (it was a cough, not speech)
# and receives {"type": "ready"}, {"type": "partial"|"final", "id": n, "text": ...}, {"type": "error"}.

MAX_UTTERANCE_SECONDS = 60
_voice_seconds: dict = {}   # user id → (day, seconds of speech sent today); per process
_open_sockets: dict = {}    # user id → open listen sockets


def _allowed_origin(origin: str | None) -> bool:
    if not origin:  # not a browser (CLI, tests): the token still has to be valid
        return True
    allowed = f"{settings.allowed_origins},{settings.desktop_origins}".split(",")
    return origin in {o.strip() for o in allowed if o.strip()}


def _spend(user_id: str, seconds: float) -> bool:
    """Count speech toward today's limit; False once it is used up."""
    day = time.strftime("%Y-%m-%d")
    d, used = _voice_seconds.get(user_id, (day, 0.0))
    used = (used if d == day else 0.0) + seconds
    _voice_seconds[user_id] = (day, used)
    return used <= settings.daily_voice_minutes * 60


def _repo_vocabulary(user, repo_id: str) -> dict:
    if not repo_id:
        return {}
    from ..main import get_store  # here, not at import time: main imports this router

    with dbmod.SessionLocal() as db:
        try:
            return vocabulary(get_store(repo_id, user, db))
        except HTTPException:
            return {}


@router.websocket("/api/voice/listen")
async def listen(ws: WebSocket):
    if not _allowed_origin(ws.headers.get("origin")):
        await ws.close(code=1008)
        return
    await ws.accept()
    send = ws.send_json
    try:
        hello = json.loads(await asyncio.wait_for(ws.receive_text(), 10))
        with dbmod.SessionLocal() as db:
            user = _user_from_token(db, str(hello.get("token", "")))
    except (asyncio.TimeoutError, ValueError, HTTPException, WebSocketDisconnect):
        await ws.close(code=1008)
        return
    uid = str(user.id)
    if _open_sockets.get(uid, 0) >= 2:
        await send({"type": "error", "message": "voice is already open in another tab"})
        await ws.close(code=1008)
        return
    if not stt.available():
        await send({"type": "error", "message": "speech recognition is not configured"})
        await ws.close(code=1011)
        return
    _open_sockets[uid] = _open_sockets.get(uid, 0) + 1
    vocab = await asyncio.to_thread(_repo_vocabulary, user, str(hello.get("repo_id") or ""))
    await send({"type": "ready", "stt": "transcribe", "language": settings.transcribe_language})

    deadline = time.time() + settings.voice_session_minutes * 60
    current: stt.Utterance | None = None
    uid_n = 0
    received = 0  # bytes of audio in the current utterance

    async def finish(u: stt.Utterance, n: int) -> None:
        heard = await u.finish()
        if u.error and not heard:
            await send({"type": "error", "id": n, "message": "couldn't transcribe that"})
            return
        await send({"type": "final", "id": n, "text": correct(heard, vocab), "heard": heard})

    try:
        while time.time() < deadline:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                if current is not None:
                    received += len(msg["bytes"])
                    if received > MAX_UTTERANCE_SECONDS * stt.SAMPLE_RATE * 2:
                        continue  # a stuck "speaking" state must not stream forever
                    await current.feed(msg["bytes"])
                continue
            kind = json.loads(msg.get("text") or "{}").get("type")
            if kind == "start":
                if current is not None:
                    await current.cancel()
                if not _spend(uid, 0):
                    await send({"type": "error", "message": "today's voice limit is used up"})
                    continue
                uid_n += 1
                n = uid_n

                async def partial(text: str, n=n) -> None:
                    await send({"type": "partial", "id": n, "text": correct(text, vocab)})

                current, received = stt.Utterance(partial), 0
                asyncio.create_task(current.open())
            elif kind == "end" and current is not None:
                u, current = current, None
                _spend(uid, received / (stt.SAMPLE_RATE * 2))
                asyncio.create_task(finish(u, uid_n))
            elif kind == "cancel" and current is not None:
                u, current = current, None
                asyncio.create_task(u.cancel())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if current is not None:
            await current.cancel()
        _open_sockets[uid] = max(0, _open_sockets.get(uid, 1) - 1)
        try:
            await ws.close()
        except RuntimeError:
            pass
