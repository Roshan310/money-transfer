# Money Transfer System

An API-only backend assignment using FastAPI, SQLAlchemy, PostgreSQL, Alembic,
and pytest. Account creation, lookup, atomic idempotent transfers, and paginated
transaction history are implemented.

## Run locally

Requires [uv](https://docs.astral.sh/uv/) and Docker with Docker Compose.
Compose credentials are for local development only.
Python dependencies live in this project's `.venv`. Compose uses the dedicated
`money-transfer-assignment` project, with development PostgreSQL on port 5433 and
test PostgreSQL on port 5434; it does not use the system PostgreSQL instance.

```bash
uv sync
cp .env.example .env
docker compose up -d --wait db test-db
uv run alembic upgrade head
uv run fastapi dev
```

The API runs at http://127.0.0.1:8000. Interactive API documentation is at
http://127.0.0.1:8000/docs; the OpenAPI schema is at `/openapi.json`.
You can also provide `DATABASE_URL` and `TEST_DATABASE_URL` as environment
variables instead of using `.env`.

## Run with Docker

```bash
docker compose up --build -d --wait api test-db
```

This builds the API with locked Python dependencies, waits for PostgreSQL,
runs Alembic in a one-off migration container, then starts the API as a non-root
user on http://127.0.0.1:8000. Do not run the local API and Docker API on the same
port simultaneously. PostgreSQL ports and the existing development volume remain
unchanged. `.env` and local caches are excluded from the image; Compose provides
the container database URL explicitly.

The migration service must finish successfully before the API starts. When
upgrading, check `docker compose logs migrate api` if startup fails. Schema
changes never delete or rewrite account balances. If existing data violates a
new constraint, migration validation fails rather than modifying that data.

## Accounts

```bash
curl -i http://127.0.0.1:8000/accounts \
  -H 'Content-Type: application/json' \
  -d '{"owner_name":"Alice","opening_balance":"100.00"}'

curl http://127.0.0.1:8000/accounts/<id-from-create-response>
```

Creation returns `201`; lookup returns `200`, or `404` if the account does not
exist. Both return `id`, `owner_name`, `balance`, and `created_at`. Invalid
requests return `422`. Errors use FastAPI's standard `detail` field.

## Transfer money

Create two accounts first, then send their IDs and a positive decimal amount:

```bash
curl -i http://127.0.0.1:8000/transfers \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: transfer-example-1' \
  -d '{"source_account_id":"<source-uuid>","destination_account_id":"<destination-uuid>","amount":"10.00"}'
```

`POST /transfers` returns `201` with `id`, `source_account_id`,
`destination_account_id`, `amount`, and `created_at`. It requires an
`Idempotency-Key` header: an opaque, nonblank string of at most 128 characters.
Keys are compared exactly and are globally unique because authentication is
outside this assignment's scope.

Repeat a successful request with the same key and equivalent payload to receive
the original `201` response, including the same ID and timestamp, without moving
money again. Decimal strings such as `"10"` and `"10.00"` are equivalent. Current
balances are deliberately excluded from the response because they can change
after a transfer. Successful keys are retained permanently and survive app
restarts. Use a new key for a new transfer, even if its payload is identical.

Errors use the existing `detail` field:

| Status | Meaning |
| --- | --- |
| `422` | Invalid IDs, missing/invalid key, invalid amount, unknown fields, or identical source and destination |
| `404` | Source or destination account does not exist |
| `409` | Insufficient funds, destination balance limit exceeded, or a committed key reused for a different transfer |

Failed requests do not reserve their keys. For example, a request rejected for
insufficient funds can be retried with the same key after funding the account.
After a network error or uncertain response, retry with the same key to safely
discover whether the transfer committed. There are no automatic application
retries or process-local locks.

## Transaction history

```bash
curl 'http://127.0.0.1:8000/accounts/<account-uuid>/transactions?limit=20&offset=0'
```

Returns `200` with `items`, `limit`, `offset`, and `has_more`. Each item contains
the public transfer fields above plus `direction`: `debit` for an outgoing
transfer or `credit` for an incoming transfer. Amounts are always positive decimal
strings. Idempotency keys are not exposed.

History includes only committed transfers involving the requested account; an
opening balance is not a transfer. Existing accounts with no history return an
empty page. Missing accounts return `404`; invalid UUIDs or pagination return
`422`. Limit defaults to 20 and accepts 1–100; offset defaults to 0 and must be
nonnegative. `has_more` is determined by fetching one extra record, without a
separate total-count query.

Results are ordered by `created_at DESC, id DESC`, with the ID breaking timestamp
ties deterministically. Timestamps represent transaction creation, not guaranteed
commit order. Offset pagination is deliberately simple for this assignment:
new transfers may shift entries between page requests, and deep offsets cost
more than cursor pagination.

## Error contract

All errors use a JSON object with a `detail` field. Expected HTTP errors contain
a string; FastAPI request-validation errors contain the standard list of field
errors. Unexpected failures return `500` with `{"detail":"Internal server error"}`;
exception details are logged server-side, not returned to clients. Existing
status codes and error bodies are preserved. OpenAPI documents success,
validation, business-error, and server-error responses.

## Design decisions

- Accounts have generated UUIDs, a trimmed owner name (1–100 characters), a
  balance, and a timezone-aware creation timestamp. Owner names need not be unique.
- All amounts share one currency with two decimal places. Money enters the API
  as decimal strings, is handled with Python `Decimal`, and is stored in
  PostgreSQL `NUMERIC(18, 2)`. Responses use strings with two decimal places.
  Negative, nonfinite, out-of-range, and overprecision inputs are rejected,
  without rounding. Unknown request fields are rejected.
- Account creation accepts an optional nonnegative opening balance, defaulting
  to zero. This is an assignment simplification for initial funding, not a
  production deposit mechanism.
- Routers handle HTTP, schemas validate input/output, services own business
  logic and transaction boundaries, and repositories perform database operations.
  Synchronous SQLAlchemy uses one session per request with synchronous endpoints.
- Creation commits before returning success and rolls back on failure.
  PostgreSQL also enforces nonnegative, finite balances within the supported
  range. UUID lookup uses the primary-key index, so no additional account index
  is needed.
- Transfers use one PostgreSQL transaction for the transfer record and both
  balance updates. Account rows are locked with `SELECT ... FOR UPDATE` in UUID
  order, preventing competing transfers from reading stale balances and avoiding
  deadlocks between opposite-direction transfers. Balances are checked while
  locks are held. Commit happens before success is returned; failures roll back
  all three writes.
- A unique database constraint reserves each successful transfer's idempotency
  key. `INSERT ... ON CONFLICT DO NOTHING RETURNING` handles simultaneous reuse.
  The key is reserved after acquiring account locks, so implicit foreign-key
  locks cannot precede the explicit lock ordering. A losing request fetches the
  committed result in a separate statement at PostgreSQL's default
  `READ COMMITTED` isolation. Identical requests replay; changed payloads conflict.
- The transfers table has foreign keys, a positive finite amount constraint, and
  a constraint preventing self-transfers. Its primary key and unique idempotency
  constraint provide indexes for transfer identity and replay queries. Composite
  indexes on `(source_account_id, created_at, id)` and
  `(destination_account_id, created_at, id)` support both sides of account history
  and cover the foreign-key columns without redundant standalone indexes.
- History stays in the accounts router, schemas, and service. The service checks
  account existence and determines direction; the transfer repository owns the
  database query. There is no duplicate ledger or separate transactions package.
- New history indexes are created concurrently. The finite-balance constraint
  is introduced as `NOT VALID`, then validated in a separate migration, without
  silently repairing invalid data. Concurrent DDL is not fully transactional;
  inspect and remove an invalid index before retrying a failed index migration.
- Alembic owns schema changes; the app does not create tables at startup.
  No authentication, account listing, updating, or deletion is included.

## Project structure

```text
app/
  main.py                 # Application and router registration
  config.py               # Environment-based settings
  database.py             # Engine, ORM base, session dependency
  money.py                # Shared Decimal validation and formatting
  errors.py               # Shared error schema and unexpected-error handler
  accounts/
    router.py             # Account and transaction-history HTTP endpoints
    schemas.py            # Request and response models
    models.py             # ORM account model
    service.py            # Business logic and transactions
    repository.py         # Database operations
  transfers/
    router.py             # Transfer endpoint and header validation
    schemas.py            # Transfer request and response models
    models.py             # ORM transfer model and constraints
    service.py            # Atomic transfer and replay logic
    repository.py         # Transfer lookup, insertion, and history queries
    errors.py             # Domain errors, without HTTP dependencies
alembic/                  # Migration configuration and revisions
tests/                    # Schema unit tests and PostgreSQL integration tests
```

## Verify

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Integration tests apply Alembic migrations to `TEST_DATABASE_URL`, then isolate
each test with a rolled-back outer transaction and savepoints. The database
must be dedicated to tests, have a name ending in `_test`, and differ from the
development database. Tests do not use SQLite or drop existing tables.
Transfer and concurrency tests use real commits and fresh sessions per request,
then delete only the records they created. Database statement and lock timeouts
bound test waits; these settings are confined to the test engine.

The concurrency tests start requests behind a barrier and hold account locks
until PostgreSQL reports that every request is waiting. They cover competing
withdrawals, simultaneous credits, opposite-direction transfers, duplicate keys,
and changed payloads sharing a key, including disjoint account pairs. Assertions
check balances, conserved money, and persisted transfer counts. An injected
failure after balance writes verifies rollback through fresh database connections.

Schema tests can run without PostgreSQL:

```bash
uv run pytest -m 'not integration'
```

To generate future migrations after modifying ORM models:

```bash
uv run alembic revision --autogenerate -m "describe the schema change"
uv run alembic upgrade head
```

Review generated migrations before applying them. Stop local databases with
`docker compose stop` when finished; the development database uses a named volume.

## Assignment coverage

| Priority | Implemented |
| --- | --- |
| P0 | All four endpoints; atomic transfers; ordered database locks; validation and status codes; Decimal money; automated concurrency tests |
| P1 | Persistent idempotency; database constraints and indexes; JSON errors; bounded history pagination; interactive OpenAPI documentation |
| P2 | Separate HTTP, schemas, business logic, and data access; Alembic migrations; API/PostgreSQL Docker Compose; unit and PostgreSQL integration tests |

Tests additionally cover incoming/outgoing history, timestamp ties, pagination,
failed-transfer exclusion, replay deduplication, sanitized server errors,
database rejection of `NaN`, and migration preservation of existing records.
Migration upgrade/downgrade tests use a private temporary schema, never the
development schema. Stretch features are intentionally excluded to keep the
assignment focused on correctness and maintainability.
