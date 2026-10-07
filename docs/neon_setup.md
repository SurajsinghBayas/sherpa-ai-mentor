# Neon Postgres setup (prod DB)

Local dev needs nothing (SQLite fallback). For staging/prod:

## 1. Create the database

1. Sign up at [neon.tech](https://neon.tech) → New Project → name `sherpa` → region closest to your API.
2. Copy the **pooled** connection string, e.g.
   `postgresql://sherpa_owner:…@ep-cool-123.us-east-2.aws.neon.tech/sherpa?sslmode=require`
3. Convert the scheme for SQLAlchemy + psycopg:
   `postgresql+psycopg://sherpa_owner:…@ep-cool-123.us-east-2.aws.neon.tech/sherpa?sslmode=require`

## 2. Configure the API

```bash
export DATABASE_URL="postgresql+psycopg://…?sslmode=require"
export JWT_SECRET_KEY="$(openssl rand -hex 32)"
export ENCRYPTION_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

Tables auto-create on startup (`init_db`). Verify:

```bash
curl localhost:8000/health  # {"db":"postgres",...}
```

## 3. Notes

- **Pooling:** Neon's pooled endpoint (`-pooler`) recommended; SQLAlchemy adds `pool_pre_ping` + recycle.
- **Branches:** use a Neon branch per preview environment; point `DATABASE_URL` at it.
- **Backups:** PITR is on by default on paid plans; free tier keeps 7-day history via branches.
- **Migrations:** current `create_all` is fine pre-launch; adopt Alembic before the schema's second breaking change.
- **Secrets:** never commit keys — users' LLM keys are Fernet-encrypted in `provider_keys`/`custom_endpoints`; only `last4` ever leaves the API.
