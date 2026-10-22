# Grounding eval — fastapi/full-stack-fastapi-template

_Run 2026-10-22 18:17 · model `qwen.qwen3-coder-480b-a35b-instruct` · retrieval keyword + pgvector (`amazon.titan-embed-text-v2:0`) · commit `b1125d8`. Regenerate with `make eval`._

| Metric | Value |
|---|---|
| Questions | 10 |
| Citation validity (verified / all cited) | 98% (56 kept, 1 removed) |
| Answers with ≥1 verified citation | 10/10 |
| Cites the file a maintainer would point to | 90% |
| Median latency | 3.25 s |
| Offline fallbacks | 0 |

| Question | Hit | Verified | Removed | Seconds | Cited files |
|---|---|---|---|---|---|
| What happens when a user signs up? | ✅ | 4 | 0 | 3.6 | `backend/app/api/routes/users.py`, `frontend/src/hooks/useAuth.ts`, `frontend/src/routes/signup.tsx` |
| How does login work and where is the access token created? | ✅ | 7 | 0 | 2.6 | `backend/app/api/deps.py`, `backend/app/api/routes/login.py`, `backend/app/core/security.py`, `frontend/src/client/core/auth.gen.ts` |
| How are passwords hashed and verified? | ✅ | 4 | 0 | 3.0 | `backend/app/core/security.py`, `backend/app/crud.py`, `backend/app/models.py`, `backend/app/utils.py` |
| How does the backend know which user is making a request? | ✅ | 7 | 0 | 2.8 | `backend/app/api/deps.py`, `backend/app/api/routes/items.py`, `backend/app/api/routes/users.py` |
| Where are the database models defined? | ✅ | 7 | 1 | 4.2 | `backend/README.md`, `backend/app/alembic/env.py`, `backend/app/alembic/versions/e2412789c190_initialize_models.py`, `backend/app/core/config.py` |
| How does password recovery send an email? | ✅ | 4 | 0 | 2.7 | `backend/app/api/routes/login.py`, `backend/app/core/config.py`, `backend/app/utils.py`, `frontend/src/routes/recover-password.tsx` |
| Where is the application configuration loaded from? | ✅ | 8 | 0 | 3.6 | `backend/app/alembic/env.py`, `backend/app/api/main.py`, `backend/app/core/config.py`, `deployment.md` |
| How does the frontend call the backend API? | ✅ | 6 | 0 | 4.1 | `frontend/src/client/sdk.gen.ts`, `frontend/src/hooks/useAuth.ts`, `frontend/src/main.tsx` |
| How are database migrations managed? | ❌ | 2 | 0 | 3.2 | `backend/README.md`, `backend/app/core/db.py` |
| Who is allowed to create or delete other users? | ✅ | 7 | 0 | 3.3 | `backend/app/api/deps.py`, `backend/app/api/routes/users.py`, `backend/app/models.py`, `frontend/src/components/Admin/AddUser.tsx` |
