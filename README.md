# Money Transfer System

> [!WARNING]
> This part of repository (README.md) is a pure human slop. I have tried my best to make it as clean and readable as possible


This is a API only, money transfer system, which allows creation of accounts and transfer money (virtual) among those accounts.

In between these simple process, lies a good amount of reliability and consistency check. 

The main focus is making transfers safe: either both balances change and the
transfer is recorded, or nothing changes. Retrying a successful request must not
move money twice.

This is built using Python 3.12, FastAPI, PostgreSQL, SQLAlchemy, Alembic. 

## Setup and run

Requirements: 

1. `Docker`

That's it. 

### Run everything with Docker

Run the following commands, one step at a time.

```bash
1. git clone https://github.com/Roshan310/money-transfer.git

2. cd money-transfer

3. cp .env.example .env

4. docker compose up --build -d --wait api
```

Visit the following URL to test the API.

- API: http://127.0.0.1:8000
- Interactive API docs: http://127.0.0.1:8000/docs
- OpenAPI schema: http://127.0.0.1:8000/openapi.json



After changing the code, rebuild the API image with
`docker compose up --build -d --wait api`. Restarting a container alone does not
pick up code changes because the source is copied into the image.

To stop the running containers:
```bash
docker compose stop
```



## Using the API

All account and transfer routes use `/api/v1`.

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/accounts` | Create an account |
| `GET` | `/api/v1/accounts` | List accounts, mainly to find IDs while making a transer (development purpose only) |
| `GET` | `/api/v1/accounts/{id}` | Get an account and its current balance |
| `POST` | `/api/v1/transfers` | Transfer money between two accounts |
| `GET` | `/api/v1/accounts/{id}/transactions` | Get incoming and outgoing transfers |

Create two accounts through `/docs`, and use `/api/v1/transfers` route to send money (not real one).

I implemented a `GET /api/v1/accounts`, which retrieves all the account with their uuid, to make it easy to test the `/api/v1/transfers` route. THIS IS NOT SAFE FOR PRODUCTION OBVIOUSLY.



## Decisions and trade-offs

1. Synchronous design instead of Async.

    I chose synchronous design because async wasn't necessary for the correcteness and reliability. FastAPI can execute synchronous blocking routes in its thread pool, while PostgreSQL handles the actual _transfer_ concurrency through transactions and row locks.
    Async definitely could improve I/O scalability and at much much higher concurrency but it wouln't change the transactional guarantees, so I prefered simpler implementation. 

2. A _transfer_ record and both balance updates share one database transaction.
  Both account rows are locked with `SELECT ... FOR UPDATE` (uses SQLAlchemy ORM instaed of this raw SQL), always in UUID
  order. Balance checks happen while those locks are held. This serializes
  _transfers_ involving the same account and avoids opposite-direction lock
  ordering problems, at the cost of throughput for busy accounts.


3. Money uses Python `Decimal` and PostgreSQL `NUMERIC(18, 2)`, never floats.
  Values are validated rather than rouding off silently. This assumes one currency
  with two decimal places; currency conversion was outside the scope of this task.

4. Idempotency is stored in PostgreSQL with a unique constraint, not in memory.
  Competing requests use `INSERT ... ON CONFLICT` to resolve key reuse. Keys
  are reserved after locking accounts and kept permanently for successful
  _transfers_. They are globally scoped because the API has no authentication.

5. Database constraints protect balances, transfer amounts, account references,
  and key uniqueness. Separate source and destination history indexes support
  queries for either side of a transfer. Alembic manages schema changes and the
  app does not create tables on startup.
6. Transaction history (in `/api/v1/accounts/{account_id}/transactions`) uses offset pagination because it is simple to use and sufficient
  here. New _transfers_ can shift pages between requests, and large offsets get
  slower. Account listing is a testing convenience and is not paginated.



## Priorities and what I left out

I focused mainly on three pillars of robust payment system:
  1. Atomic transfers
  2. Safe concurrent requests
  3. Persistent Idempotency

I prioritized correctness, consistency and clear engineering decisions over unnecessary features, as mentioned. I have also made sure that pagination, database migration, proper validation, error handling, automated testing are robust, along with docker setup.


I thought about adding multiple features for a production grade money transfer system, like user authentication/authorization, rate limiting, caching, etc. but these didn't make any sense as it would only add more code to review without adding any real value to core task. 


I left out authentication, account editing and deletion, external payments, and
multi-currency support. Those need their own rules and security
decisions; adding them here would distract from the transfer behavior. Apart
from the account-listing helper, there are no stretch features.

## Features to add with more time in hand

TL;DR

1. Add cursor based pagination instead of limit-offset.
2. User authentication/authorization.
3. Double entry ledger to record debit and credit entries for every _transfer_.
4. Rate limiting on write endpoints to protect API from excessive abuse.
5. Async database access.

This is not  a _safe-to-expose_ public banking API. There is no authentication
or account ownership check: anyone who can reach it can read accounts and submit
transfers. 

Offset pagination is simple, but it becomes less efficient on large transaction tables and can produce inconsistent pages when new transactions are inserted between requests. Cursor-based pagination would use something like (created_at, id) as the cursor, giving more stable and scalable transaction-history pagination.


I would add User entity, so that every account is linked to a unique user. For now, _account_ is an individual entity with just a name and balance.

Instead of only updating account balances, every transfer could also create two immutable ledger entries, a debit for the source account and a credit for the destination account. This provides a much stronger audit trail, because every movement of money is explicitly recorded.

Endpoints such as POST /api/v1/transfers could be rate-limited to protect the service from abuse, accidental request floods, or excessive traffic. In a production level system, this would typically use a shared store such as Redis rather than process-local counters.


i have used synchronous SQLAlchemy because it keeps the transaction logic simpler and is sufficient for the scope of the assignment. If profiling showed that the service needed to handle much higher I/O concurrency, the persistence layer could be migrated to SQLAlchemy AsyncSession with an async PostgreSQL driver. This would improve I/O scalability, but it would not replace the database transactions, row locks, and constraints that provide correctness.
