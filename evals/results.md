# Grounding eval — fastapi/full-stack-fastapi-template

_Run 2026-10-21 00:13 · model `moonshotai.kimi-k2.5` · retrieval keyword + pgvector (`amazon.nova-2-multimodal-embeddings-v1:0`) · commit `b1125d8`. Regenerate with `make eval`._

| Metric | Value |
|---|---|
| Questions | 10 |
| Citation validity (verified / all cited) | 97% (65 kept, 2 removed) |
| Answers with ≥1 verified citation | 10/10 |
| Cites the file a maintainer would point to | 100% |
| Median latency | 4.550000000000001 s |
| Offline fallbacks | 0 |

| Question | Hit | Verified | Removed | Seconds | Cited files |
|---|---|---|---|---|---|
| What happens when a user signs up? | ✅ | 8 | 0 | 5.1 | `backend/app/api/routes/users.py`, `frontend/src/client/sdk.gen.ts`, `frontend/src/hooks/useAuth.ts`, `frontend/src/routes/signup.tsx` |
| How does login work and where is the access token created? | ✅ | 8 | 0 | 4.7 | `backend/app/api/deps.py`, `backend/app/api/routes/login.py`, `backend/app/core/security.py`, `backend/app/models.py` |
| How are passwords hashed and verified? | ✅ | 4 | 0 | 4.9 | `backend/app/api/routes/users.py`, `backend/app/core/security.py`, `backend/app/crud.py`, `backend/app/models.py` |
| How does the backend know which user is making a request? | ✅ | 8 | 0 | 4.4 | `backend/app/api/deps.py`, `backend/app/api/routes/items.py`, `backend/app/api/routes/login.py`, `backend/app/api/routes/users.py` |
| Where are the database models defined? | ✅ | 6 | 2 | 3.7 | `backend/README.md`, `backend/app/api/deps.py`, `backend/app/core/db.py`, `backend/app/models.py` |
| How does password recovery send an email? | ✅ | 9 | 0 | 5.6 | `backend/app/api/routes/login.py`, `backend/app/core/config.py`, `backend/app/email-templates/reset_password.html`, `backend/app/utils.py` |
| Where is the application configuration loaded from? | ✅ | 7 | 0 | 4.0 | `backend/app/api/main.py`, `backend/app/core/config.py`, `backend/app/main.py`, `compose.yml` |
| How does the frontend call the backend API? | ✅ | 6 | 0 | 4.3 | `frontend/src/client/core/auth.gen.ts`, `frontend/src/client/index.ts`, `frontend/src/hooks/useAuth.ts`, `frontend/src/main.tsx` |
| How are database migrations managed? | ✅ | 4 | 0 | 4.7 | `backend/README.md`, `backend/alembic.ini`, `backend/app/core/db.py` |
| Who is allowed to create or delete other users? | ✅ | 5 | 0 | 4.0 | `backend/app/api/deps.py`, `backend/app/api/routes/users.py`, `frontend/src/components/Admin/AddUser.tsx`, `frontend/src/components/Admin/UserActionsMenu.tsx` |
