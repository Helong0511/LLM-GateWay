.PHONY: dev test lint migrate smoke openapi

dev:
	docker compose --env-file .env -f deploy/docker-compose.yml up --build

test:
	uv run --project apps/api pytest
	cd apps/web && pnpm test

lint:
	cd apps/api && uv run ruff check app alembic
	cd apps/api && uv run mypy app
	cd apps/web && pnpm lint

migrate:
	cd apps/api && uv run alembic upgrade head

openapi:
	cd apps/api && uv run python -c "import json; from pathlib import Path; from app.main import create_app; Path('../../apps/web/openapi.json').write_text(json.dumps(create_app().openapi(), ensure_ascii=False, indent=2), encoding='utf-8')"
	cd apps/web && pnpm generate:api

smoke:
	powershell -NoProfile -File scripts/smoke.ps1
