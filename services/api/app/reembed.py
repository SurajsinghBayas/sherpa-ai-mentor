"""Give every saved repo vectors from the current EMBEDDING_MODEL: `make reembed`.

Run it after changing the embedding model. Vectors are keyed by (model, text_hash), so
chunks that already have one are skipped and the old model's vectors are left alone.
Until a repo is done, its searches fall back to keywords + TF-IDF.
"""
import logging
import sys

from sqlalchemy import select

from . import db as dbmod
from .config import load_local_env
from .dbmodels import Repo
from .embeddings import embedder
from .persist import SqlBackend, embed_input, text_hash, vectors_supported


def main() -> int:
    load_local_env()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per request is noise
    if not (embedder.available and vectors_supported()):
        print("embeddings unavailable: needs AWS_BEARER_TOKEN_BEDROCK and Postgres with pgvector")
        return 1
    with dbmod.SessionLocal() as db:
        repos = db.execute(select(Repo.id, Repo.owner_id, Repo.name)
                           .where(Repo.private.is_(False))).all()
    print(f"model {embedder.model}: {len(repos)} repo(s)")
    for rid, owner, name in repos:
        backend = SqlBackend(rid, owner)
        loaded = backend.load()
        if not loaded:
            continue
        chunks = loaded[0]
        print(f"- {name} ({len(chunks)} chunks)")
        backend._ensure_embeddings(chunks, [text_hash(embed_input(c)) for c in chunks])
    return 0


if __name__ == "__main__":
    sys.exit(main())
