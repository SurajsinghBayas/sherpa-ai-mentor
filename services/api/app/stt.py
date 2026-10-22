"""Speech-to-text with Amazon Transcribe streaming, one stream per utterance.

The browser decides when someone is speaking (Silero VAD) and streams just that audio, so a
stream opens when the user starts talking and closes when they stop: no audio of silence or
of Sherpa's own voice is sent or billed. Partial results arrive while they talk (~0.7s in);
the final text ~0.5s after they stop.
"""
import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

from .config import settings

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
AUTH_RETRY_AFTER = 300   # after bad credentials, use the browser's recognition for a while
_down_until = 0.0


def _credentials():
    """Static AWS credentials for Transcribe, or None when there are none."""
    if settings.transcribe_access_key_id and settings.transcribe_secret_access_key:
        return (settings.transcribe_access_key_id, settings.transcribe_secret_access_key, None)
    import boto3

    creds = boto3.Session().get_credentials()  # env vars, ~/.aws, or an instance role
    if creds is None:
        return None
    frozen = creds.get_frozen_credentials()
    return (frozen.access_key, frozen.secret_key, frozen.token)


def available() -> bool:
    if not settings.transcribe_enabled or time.time() < _down_until:
        return False
    try:
        import amazon_transcribe  # noqa: F401
    except ImportError:
        return False
    try:
        return _credentials() is not None
    except Exception:  # noqa: BLE001 — a broken ~/.aws must not break voice
        return False


class Utterance:
    """One spoken turn: feed PCM16 audio, get partial text as it comes, then the final text."""

    def __init__(self, on_partial: Callable[[str], Awaitable[None]]):
        self.on_partial = on_partial
        self.finals: list[str] = []
        self._stream = None
        self._reader: Optional[asyncio.Task] = None
        self._opened = asyncio.Event()
        self._pending: list[bytes] = []   # audio that arrived while the stream was opening
        self.error: Optional[str] = None

    async def open(self) -> None:
        global _down_until
        from amazon_transcribe.auth import StaticCredentialResolver
        from amazon_transcribe.client import TranscribeStreamingClient

        try:
            creds = _credentials()
            if creds is None:
                raise RuntimeError("no AWS credentials for Transcribe")
            client = TranscribeStreamingClient(
                region=settings.transcribe_region,
                credential_resolver=StaticCredentialResolver(
                    access_key_id=creds[0], secret_access_key=creds[1], session_token=creds[2]))
            self._stream = await client.start_stream_transcription(
                language_code=settings.transcribe_language, media_sample_rate_hz=SAMPLE_RATE,
                media_encoding="pcm", enable_partial_results_stabilization=True,
                partial_results_stability="medium")
        except Exception as e:  # noqa: BLE001 — SDK raises many types
            msg = str(e)
            if any(s in msg for s in ("UnrecognizedClient", "InvalidSignature", "AccessDenied",
                                      "SubscriptionRequired", "security token")):
                _down_until = time.time() + AUTH_RETRY_AFTER
            self.error = f"{type(e).__name__}: {msg[:200]}"
            log.warning("transcribe: could not open a stream (%s)", self.error)
            self._opened.set()
            return
        self._reader = asyncio.create_task(self._read())
        # drain what arrived while opening; feed() keeps buffering until _opened is set, and
        # nothing awaits between the last pop and set(), so no chunk can slip between them
        while self._pending:
            await self._stream.input_stream.send_audio_event(audio_chunk=self._pending.pop(0))
        self._opened.set()

    async def feed(self, pcm: bytes) -> None:
        if self.error:
            return
        if not self._opened.is_set():
            self._pending.append(pcm)
            return
        try:
            await self._stream.input_stream.send_audio_event(audio_chunk=pcm)
        except Exception as e:  # noqa: BLE001
            self.error = str(e)[:200]

    async def _read(self) -> None:
        try:
            async for event in self._stream.output_stream:
                results = getattr(getattr(event, "transcript", None), "results", None) or []
                partial = ""
                for r in results:
                    if not r.alternatives:
                        continue
                    if r.is_partial:
                        partial = r.alternatives[0].transcript
                    else:
                        self.finals.append(r.alternatives[0].transcript)
                if results:
                    await self.on_partial(" ".join(self.finals + ([partial] if partial else [])).strip())
        except Exception as e:  # noqa: BLE001
            self.error = self.error or str(e)[:200]
            log.warning("transcribe: stream ended with an error (%s)", self.error)

    async def finish(self, timeout: float = 4.0) -> str:
        """End the audio and wait for the last results; returns the full final text."""
        await asyncio.wait_for(self._opened.wait(), timeout)
        if self._stream is not None and not self.error:
            try:
                await self._stream.input_stream.end_stream()
            except Exception:  # noqa: BLE001
                pass
        if self._reader is not None:
            try:
                await asyncio.wait_for(self._reader, timeout)
            except asyncio.TimeoutError:
                self._reader.cancel()
        return " ".join(self.finals).strip()

    async def cancel(self) -> None:
        if self._stream is not None:
            try:
                await self._stream.input_stream.end_stream()
            except Exception:  # noqa: BLE001
                pass
        if self._reader is not None:
            self._reader.cancel()
