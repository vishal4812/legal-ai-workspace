.PHONY: up down logs backend frontend test test-backend test-frontend migrate migration build

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

backend:
	docker compose up --build backend

frontend:
	docker compose up --build frontend

test: test-backend test-frontend

test-backend:
	docker compose run --rm --no-deps backend pytest

test-frontend:
	docker compose run --rm --no-deps frontend npm test -- --run

migrate:
	docker compose run --rm backend alembic upgrade head

migration:
	docker compose run --rm backend alembic revision --autogenerate -m "$(name)"

build:
	docker compose build
