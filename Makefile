.PHONY: api web dev test lint eval ingest ask refresh-docs

API_DIR=services/api
WEB_DIR=apps/web

# env -u: a Bedrock key exported by your shell profile would otherwise shadow the one in .env
api:
	cd $(API_DIR) && env -u AWS_BEARER_TOKEN_BEDROCK ALLOW_LOCAL_INGEST=true uvicorn app.main:app --reload --port 8000

web:
	cd $(WEB_DIR) && npm run dev

dev:
	docker compose up --build

test:
	cd $(API_DIR) && python -m pytest -q

lint:
	cd $(API_DIR) && (ruff check app tests || true) && python -m compileall -q app

eval:
	cd $(API_DIR) && python ../../evals/run_eval.py

ingest:
	curl -s -X POST localhost:8000/api/ingest -H 'Content-Type: application/json' -d '{"repo_url":"https://github.com/fastapi/full-stack-fastapi-template"}' | head -c 2000; echo

refresh-docs:
	@echo "POST /api/freshness with your docs markdown to detect stale sections (see docs/demo_script.md)"
