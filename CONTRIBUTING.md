# Contributing

1. Fork + branch: `feat/<short-name>`.
2. Backend: `cd services/api && pip install -r requirements.txt && python -m pytest -q`.
3. Frontend: `cd apps/web && npm install && npm run dev`.
4. Every agent answer must add/keep citations — update `tests/test_grounding.py` if you touch retrieval or prompts.
5. Run `ruff check` (or `make lint`) before pushing. CI runs pytest + tsc.
6. Easiest first PR: run Sherpa on itself (`POST /api/ingest-self` → `/api/tasks`) and pick a task.
