# Digital Wallet API

A production-style **digital wallet & financial transaction system** built with FastAPI,
SQLAlchemy 2.0, and PostgreSQL. Users hold wallets, deposit/withdraw simulated funds, transfer
to other users, request payments, and get refunds — all backed by a double-entry ledger that
stays correct under concurrent access, with a React admin dashboard for support/admin staff.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full design: entities, schema, concurrency
strategy, money representation, idempotency semantics, fraud evaluation, outbox reliability, and
the complete step-by-step roadmap with what changed in the final hardening pass.

**Status:** Feature-complete for this project's scope (roadmap steps 1–15). Known, deliberately
deferred limitations are listed at the end of `ARCHITECTURE.md`.

## Features

- JWT auth (access + refresh) with RBAC (`user` / `support` / `admin`), login history
- Multi-currency wallets (ILS/USD/EUR) with `active`/`frozen`/`closed` status
- A double-entry ledger — `wallets.balance` is a cache, `ledger_entries` is the source of truth
  and can always rebuild it (`ledger_service.rebuild_balance`)
- Deposits, withdrawals, transfers, refunds, and admin/support reversals, all under row-level
  locking (`SELECT ... FOR UPDATE`) with fixed lock ordering to prevent deadlocks
- Idempotency-Key support on every money-moving endpoint, scoped per user
- Configurable per-role/per-user transfer limits
- A small configurable fraud rules engine (large amount, transfer velocity, new-recipient-large-amount)
- An immutable, insert-only audit log — including failed transaction attempts, not just successes
- A transactional outbox + worker for async notifications, safe for multiple worker replicas
  (`SELECT ... FOR UPDATE SKIP LOCKED`)
- Admin dashboard: user management, wallet explorer + freeze/unfreeze, transaction explorer,
  fraud rules/events, audit log viewer, live stats

## Tech stack

Backend: Python, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, PostgreSQL, Redis, pytest.
Frontend: React, TypeScript, Vite, React Router, TanStack Query.
Infra: Docker Compose, GitHub Actions CI (backend + frontend + a real-Postgres concurrency job).

## Repository structure

```
app/           FastAPI backend — core/, models/, schemas/, services/, api/v1/ (see ARCHITECTURE.md §5)
workers/       outbox_worker.py — polls outbox_events, dispatches async notifications
alembic/       database migrations
scripts/       seed.py — development demo data, run through the real service layer
tests/         pytest suite (unit, integration, concurrency, ledger-integrity, idempotency)
frontend/      React + TS + Vite admin dashboard
```

---

## Quick start

### Backend (SQLite)

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Open **http://localhost:8000/docs** for interactive Swagger UI (OpenAPI docs with request/response
examples for every endpoint).

### Demo data

```bash
python -m scripts.seed     # or: make seed
```

Populates realistic demo data through the real service layer (not raw inserts) — users, wallets
(including a frozen one), completed/failed transactions, a refund, a payment request, and a fraud
rule with a triggered event. Safe to re-run; each step is skipped if already seeded.

**Demo credentials — local development only, never reuse anywhere real** (password `Passw0rd123`
for all):

| Username | Role |
|---|---|
| `admin1` | admin |
| `support1` | support |
| `alice`, `bob`, `carol` | user |

To reset the database and reseed from scratch: `make reset-db` (drops all tables via Alembic,
re-migrates, reseeds — local development only, intentionally destructive).

### Admin dashboard (React + TS + Vite)

```bash
cd frontend
npm install
npm run dev       # http://localhost:5173, proxies /api to http://localhost:8000
```

Sign in with `admin1` or `support1` (see demo credentials above) — the dashboard rejects
`user`-role accounts.

### Docker (PostgreSQL + Redis + API + outbox worker)

```bash
docker compose up --build
```

Builds the dashboard into `frontend/dist` and bakes it into the API image (multi-stage
`Dockerfile`), runs `alembic upgrade head` on startup, and brings up Postgres, Redis, the API, and
the outbox worker — the whole stack with one command. The API serves both `/api/v1/*` and the
dashboard from the same container.

### Environment variables

See [`.env.example`](.env.example) for the full list with defaults. The important ones:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLite for local dev, `postgresql+psycopg2://...` in Docker/production |
| `SECRET_KEY` | JWT signing key — must be overridden in production |
| `REDIS_URL` | Rate limiting / idempotency cache (optional locally, required for multi-instance) |
| `CORS_ORIGINS` | Allowed dashboard origins |
| `DEFAULT_MAX_TRANSACTION_AMOUNT`, `DEFAULT_DAILY_TRANSFER_LIMIT`, `DEFAULT_DAILY_WITHDRAWAL_LIMIT` | Fallback transfer limits when no `TransferLimitPolicy` row matches |

### Database migrations

```bash
alembic upgrade head           # apply all migrations
alembic downgrade base         # roll back to empty (local dev only)
alembic revision --autogenerate -m "description"   # after changing a model
alembic check                  # confirm models match the latest migration (no drift)
```

### Tests

```bash
pytest                                        # backend tests + coverage report
pytest tests/test_postgres_concurrency.py     # real-Postgres concurrency tests (needs POSTGRES_TEST_DATABASE_URL — see below)
ruff check app tests                          # backend lint
ruff format --check app tests                 # backend format check
cd frontend && npx tsc -b                     # frontend typecheck
cd frontend && npm run lint                   # frontend lint (oxlint)
cd frontend && npm run build                  # frontend production build
```

The real-Postgres concurrency tests are skipped unless `POSTGRES_TEST_DATABASE_URL` is set (a
Postgres instance with a real multi-connection pool, not the single-connection SQLite the rest of
the suite uses). CI provides this via a `postgres:16-alpine` service container. To run them
locally:

```bash
docker run --rm -e POSTGRES_PASSWORD=wallet -e POSTGRES_USER=wallet -e POSTGRES_DB=wallet_test -p 5433:5432 postgres:16-alpine
POSTGRES_TEST_DATABASE_URL=postgresql+psycopg2://wallet:wallet@localhost:5433/wallet_test pytest tests/test_postgres_concurrency.py
```

---

## API documentation

Interactive OpenAPI docs (Swagger UI) are served at `/docs` and ReDoc at `/redoc` whenever the API
is running, with request/response examples generated from the Pydantic schemas. `/health` is a
combined liveness+readiness probe used by the Docker `HEALTHCHECK`; `/api/v1/health` and
`/api/v1/health/ready` are the same checks split (liveness / Postgres-readiness) for orchestrators
that want them separately.

## Known limitations

See the end of [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full, current list with rationale.
In short: refresh tokens aren't revocable, there's no admin API yet for `TransferLimitPolicy`
(only the hardcoded defaults are reachable), and the real-Postgres concurrency tests haven't been
executed in every development environment — only in CI, where a real Postgres service is
available.

---

## Why the architecture looks the way it does

- **PostgreSQL over SQLite in production** — wallet transfers need real row-level locking
  (`SELECT ... FOR UPDATE`), which SQLite cannot provide under concurrent writers. SQLite is
  used only for fast unit/integration tests that don't exercise concurrency; a dedicated CI job
  runs a second suite against real Postgres for the concurrency-sensitive scenarios.
- **Ledger, not a balance column** — `wallets.balance` is a cache; `ledger_entries` is the
  source of truth and must always be able to reconstruct it.
- **`Decimal`, not `float`, for every monetary value** — binary floating point cannot represent
  currency amounts exactly. Money is `Decimal` end to end (models, schemas, arithmetic) and is
  serialized as a JSON *string* (e.g. `"100.00"`), never a JSON number.
- **Outbox instead of a broker (for now)** — financial writes and notification events commit in
  the same DB transaction via an outbox table; a worker publishes asynchronously. A real message
  broker is Project 2 in this portfolio series (Distributed Notification Platform) — this outbox
  is designed to hand off to it later rather than duplicating that infrastructure now.

Full rationale for every decision — including the ones that changed after a deliberate reliability
and security hardening pass — is in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## License

MIT
