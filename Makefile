.PHONY: install dev test lint format migrate seed reset-db docker-up docker-down frontend-install frontend-dev frontend-build

install:
	pip install -r requirements-dev.txt

dev:
	uvicorn app.main:app --reload

test:
	pytest

lint:
	ruff check app tests

format:
	ruff format app tests && ruff check --fix app tests

migrate:
	alembic upgrade head

seed:
	python -m scripts.seed

# Local development only: drops every table (via Alembic, so it also proves the migration chain
# is reversible) and rebuilds from scratch with demo data. Never point this at anything but a
# local/dev database — it is intentionally destructive.
reset-db:
	alembic downgrade base
	alembic upgrade head
	python -m scripts.seed

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down -v

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build
