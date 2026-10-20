# AWS RDS Postgres setup (prod DB)

Local dev needs nothing (SQLite fallback, TF-IDF search). For staging/prod Sherpa uses
Amazon RDS for PostgreSQL, which also stores the pgvector embeddings.

## 1. Create the database

1. RDS → Create database → PostgreSQL **15.2 or newer** (pgvector ships with RDS from 15.2; we run 18.3).
2. Pick a region near the API (we use `ap-south-1`) and set a **long random master password**.
3. Connectivity:
   - API hosted **inside the same VPC** (App Runner with a VPC connector, ECS, EC2): keep *Publicly accessible = No*.
   - API hosted **outside AWS** (Railway, Render, your laptop): set *Publicly accessible = Yes*, then in the
     instance's security group add an inbound rule **PostgreSQL / TCP 5432** from each caller's IP only
     (e.g. `203.0.113.7/32`). Never open 5432 to `0.0.0.0/0`.
4. Copy the endpoint and build the URL (SQLAlchemy + psycopg scheme, SSL required):
   `postgresql+psycopg://postgres:<password>@<instance>.<region>.rds.amazonaws.com:5432/postgres?sslmode=require`

## 2. Configure the API

```bash
export DATABASE_URL="postgresql+psycopg://postgres:…@….rds.amazonaws.com:5432/postgres?sslmode=require"
export JWT_SECRET_KEY="$(openssl rand -hex 32)"
export ENCRYPTION_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

On startup the API runs the Alembic migrations (`services/api/migrations`), which enable the
`vector` extension and create every table, including `chunk_embeddings`. Nothing to run by hand. Verify:

```bash
curl localhost:8000/health  # {"db":"postgres", "embeddings": {"available": true}, ...}
```

## 3. Notes

- **SSL:** the API adds `sslmode=require` to any non-local Postgres URL that doesn't set it.
- **Migrations:** Alembic. Add one with `cd services/api && alembic revision -m "…"`, write `upgrade()`, and it applies on the next deploy. Concurrent replicas take a Postgres advisory lock, so only one migrates.
- **What's stored:** users, BYOK keys, study results, and every indexed repo (`repos`, `repo_files`, `repo_chunks`, `repo_artifacts`). Embeddings are in `chunk_embeddings`, keyed by content hash, so unchanged code is never re-embedded. Expect roughly 4 KB of vector per chunk (1024 floats).
- **Backups:** RDS automated backups (point-in-time restore) are on by default; check the retention period.
- **Connections:** SQLAlchemy uses `pool_pre_ping` + recycle. If you run many API replicas, add RDS Proxy.
- **Secrets:** never commit the URL. Users' LLM keys are Fernet-encrypted in `provider_keys`/`custom_endpoints`; only `last4` ever leaves the API.
