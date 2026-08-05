.PHONY: bootstrap compose-config db-up migrate seed migrate-down api up down smoke test test-integration lint check

API_CHECK = docker compose run --rm --no-deps \
	-v ./pyproject.toml:/app/pyproject.toml:ro \
	-v ./services/api/tests:/app/services/api/tests:ro \
	api

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
	$(API_CHECK) pytest -q services/api/tests -m "not integration"

test-integration:
	docker compose up -d postgres redis minio minio-init
	docker compose run --rm migrate
	docker compose run --rm seed
	docker compose run --rm \
		-v ./pyproject.toml:/app/pyproject.toml:ro \
		-v ./services/api/tests:/app/services/api/tests:ro \
		api pytest -q services/api/tests -m integration

lint:
	$(API_CHECK) sh -c 'ruff check services/api/src services/api/tests services/api/migrations && mypy services/api/src && lint-imports'

check: compose-config lint test
	docker compose build api web
