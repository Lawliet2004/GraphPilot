.PHONY: install dev-api dev-app worker migrate test lint build e2e up down
install:
	uv sync --frozen
	npm --prefix app ci
	npm ci
migrate:
	uv run alembic upgrade head
dev-api:
	uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
dev-app:
	npm --prefix app run dev
worker:
	uv run python -m api.worker
test:
	uv run pytest -q
lint:
	uv run ruff check api tests scripts migrations
	npm --prefix app run typecheck
build:
	npm --prefix app run build
e2e:
	npm run e2e
up:
	docker compose up --build -d
down:
	docker compose down
