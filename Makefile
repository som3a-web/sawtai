.PHONY: bootstrap compose-config db-up migrate seed migrate-down api up down smoke test lint

bootstrap:
	docker compose up -d --build postgres redis minio minio-init
	docker compose run --rm migrate
	docker compose run --rm seed
	docker compose up -d --build api worker web caddy

compose-config:
	docker compose config --quiet

db-up:
	docker compose up -d postgres redis minio minio-init

migrate:
	docker compose run --rm migrate

seed:
	docker compose run --rm seed

migrate-down:
	docker compose run --rm migrate alembic downgrade base

api:
	docker compose up --build api worker web caddy

up:
	docker compose up -d api worker web caddy

down:
	docker compose down

smoke:
	curl --fail --silent http://localhost:8080/api/v1/health/ready
	curl --fail --silent http://localhost:8080/api/v1/analytics/overview >/dev/null
	curl --fail --silent http://localhost:8080/api/v1/messages?limit=1 >/dev/null

test:
	docker compose run --rm api pytest

lint:
	docker compose run --rm api ruff check services/api/src services/api/tests
	docker compose run --rm api mypy services/api/src
	docker compose run --rm api lint-imports
