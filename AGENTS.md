# Working on this repo

This is an API-only backend assignment, not a production banking service.
Stack: Python 3.12+, FastAPI, synchronous SQLAlchemy, PostgreSQL 17, Alembic,
and pytest. Keep changes small and focused; do not add unrelated features.

## Where things live

- `app/main.py`: app factory, exception handler, and root status endpoint.
- `app/api.py`: shared `/api/v1` router. Old unversioned business routes are removed.
- `app/accounts/` and `app/transfers/`: feature packages. Routers handle HTTP,
  schemas validate inputs/outputs, services own business rules and transactions,
  repositories run queries, and models define database tables.
- Transaction history belongs to accounts; its queries reuse transfer records.
- `app/money.py`: shared money validation. `app/config.py` and `app/database.py`:
  settings, engine, and request-scoped sessions.
- `alembic/versions/`: migrations. `tests/`: unit, integration, and concurrency tests.

Routes: create/list accounts, get an account, get its paginated transactions,
and create transfers, all under `/api/v1`. Docs are at `/docs`; schema is at
`/openapi.json`. There is no authentication or account ownership enforcement.

## Run and verify

Run commands from the repository root. Copy `.env.example` to `.env` only if
`.env` does not exist; never overwrite existing credentials.

```bash
uv sync --locked
docker compose up --build -d --wait api
docker compose up -d --wait test-db
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Docker copies source into the image: rebuild after code changes; a restart is
not enough. For local development, start `db`, run `.venv/bin/alembic upgrade head`,
then `.venv/bin/fastapi dev`. Host processes use `DATABASE_URL`; Docker uses
`DOCKER_DATABASE_URL`.

Tests use `TEST_DATABASE_URL`, require a separate PostgreSQL database ending
in `_test`, and apply migrations automatically. Never point tests at development
data or replace PostgreSQL with SQLite for transaction/concurrency verification.

## Rules to preserve

- Use `Decimal` and `NUMERIC(18, 2)` for money, never floats. API money inputs
  are decimal strings; reject extra precision rather than silently rounding.
- Both balance updates and the transfer record must commit in one transaction.
  Lock both accounts in UUID order before checking balances or reserving a key.
- `Idempotency-Key` is required for transfers. Successful retries return the
  original transfer; changed payloads return `409`; failed requests do not reserve keys.
- Keep database constraints and history indexes. Add a new Alembic revision for
  schema changes; do not rewrite existing migrations or create tables on startup.
- Preserve response shapes and status codes unless the requested change requires
  otherwise. Run the full suite after transfer changes, including concurrency tests.
- Keep secrets in ignored `.env` files; document settings in `.env.example`.
  Do not print credentials or delete database volumes to fix setup problems.
- Preserve unrelated user edits. The user makes Git commits; do not commit unless asked.
