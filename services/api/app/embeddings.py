"""Text embeddings via Amazon Bedrock (Titan Text v2 by default, or Nova multimodal).

Uses a Bedrock API key (AWS_BEARER_TOKEN_BEDROCK) against the InvokeModel REST
endpoint, so no AWS SDK is needed. Every failure is logged; callers fall back to
TF-IDF search when embeddings are unavailable.
"""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import List, Optional

import httpx

from .config import settings

log = logging.getLogger(__name__)

MAX_CHARS = 8000  # ~2k tokens; chunks are ≤60 lines so this rarely truncates


class Embedder:
    @property
    def model(self) -> str:
        return settings.embedding_model

    @property
    def dim(self) -> int:
        return settings.embedding_dim

    @property
    def available(self) -> bool:
        return bool(settings.aws_bearer_token_bedrock and settings.embedding_model)

    def _url(self) -> str:
        region = settings.embedding_region or settings.aws_default_region
        return f"https://bedrock-runtime.{region}.amazonaws.com/model/{self.model}/invoke"

    def _body(self, text: str, purpose: str) -> dict:
        text = text[:MAX_CHARS] or " "
        if "titan-embed" in self.model:  # Titan has no query/document purpose
            return {"inputText": text, "dimensions": self.dim, "normalize": True}
        return {"taskType": "SINGLE_EMBEDDING", "singleEmbeddingParams": {
            "embeddingPurpose": purpose, "embeddingDimension": self.dim,
            "text": {"truncationMode": "END", "value": text}}}

    @staticmethod
    def _vector(data: dict) -> List[float]:
        return data["embedding"] if "embedding" in data else data["embeddings"][0]["embedding"]

    def _one(self, client: httpx.Client, text: str, purpose: str) -> List[float]:
        body = self._body(text, purpose)
        headers = {"Authorization": f"Bearer {settings.aws_bearer_token_bedrock}"}
        for attempt in range(4):
            r = client.post(self._url(), json=body, headers=headers)
            if r.status_code == 200:
                return self._vector(r.json())
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(0.5 * 2 ** attempt)
                continue
            raise RuntimeError(f"bedrock embeddings HTTP {r.status_code}: {r.text[:200]}")
        raise RuntimeError("bedrock embeddings: retries exhausted")

    def embed_documents(self, texts: List[str], on_progress=None) -> List[List[float]]:
        """Embed many texts concurrently. Raises if any request ultimately fails.

        `on_progress(done, total)` is called from worker threads as texts finish.
        """
        if not texts:
            return []
        failed = threading.Event()  # first permanent error stops the remaining requests
        done = [0]
        lock = threading.Lock()

        def one(t: str) -> List[float]:
            if failed.is_set():
                raise RuntimeError("skipped after an earlier failure")
            try:
                v = self._one(client, t, "GENERIC_INDEX")
            except Exception:
                failed.set()
                raise
            if on_progress:
                with lock:
                    done[0] += 1
                    n = done[0]
                on_progress(n, len(texts))
            return v

        with httpx.Client(timeout=30) as client, \
                ThreadPoolExecutor(max(1, settings.embedding_concurrency)) as pool:
            return list(pool.map(one, texts))

    def embed_query(self, text: str) -> Optional[List[float]]:
        if not self.available:
            return None
        try:
            return list(_cached_query(self.model, self.dim, text))
        except Exception as e:  # noqa: BLE001
            log.warning("embeddings: query embedding failed (%s); FALLBACK to TF-IDF search", e)
            return None


# one long-lived connection for questions: a fresh TLS handshake per question cost ~1 s
_query_client = httpx.Client(timeout=20)


@lru_cache(maxsize=512)
def _cached_query(model: str, dim: int, text: str) -> tuple:
    return tuple(embedder._one(_query_client, text, "GENERIC_RETRIEVAL"))


embedder = Embedder()
