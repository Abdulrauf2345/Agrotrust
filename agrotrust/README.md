# AgroTrust

An agricultural supply-chain / marketplace / escrow / farm-financing platform for Nigeria.

Built as a modular monolith in Python, with SQLite standing in for PostgreSQL and Flask
standing in for FastAPI (see `docs/adr/` for why, and the exact migration path back to the
originally-specified stack).

## Start here

- **`docs/FINAL_EVALUATION.md`** — an honest assessment of what's real, what's substituted,
  and what's not done yet. Read this first.
- **`docs/adr/`** — one file per architectural decision, especially every place this build
  diverges from a "normal" production stack.

## Requirements

- Python 3.12 (3.10+ likely works, untested)
- No external services needed to run tests or the API locally — everything (including the
  database) is self-contained.

Install dependencies:

```bash
pip install -r requirements-dev.txt
```

(`requirements.txt` alone is enough just to run the app; `-dev` adds pytest/ruff/mypy for
local development. `requirements-production.txt` is the *different*, originally-specified
FastAPI/PostgreSQL/Redis stack — not needed to run this build as-is.)

## Run the test suite

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p "test_*.py" -t .
```

Or, if you installed `pytest`:

```bash
PYTHONPATH=src pytest tests/ -v
```

You should see 188 tests pass. A few stderr lines like `job failed` and `outbox publish
failed` are expected — they're printed by tests that deliberately inject failures to prove
retry/rollback behavior works.

## Run the API locally

```bash
PYTHONPATH=src python3 scripts/run_dev_server.py
```

This uses a persistent database at `.dev_data/agrotrust_dev.db` (survives restarts; pass
`--fresh` to wipe it) and seeds a few reference crops automatically. Then, e.g.:

```bash
curl http://localhost:8000/healthz
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"phone": "+2348011111111", "password": "SecurePass123", "full_name": "Farmer Joe", "role": "FARMER"}'
```

## Exploring the API with Postman

`postman/AgroTrust.postman_collection.json` has ~99 pre-built requests covering every module,
with IDs automatically chained between requests (create a farm, its id gets reused by the next
request automatically). **See `postman/README.md` for full setup instructions** — import the
collection, run `scripts/run_dev_server.py`, and follow the one manual step for granting
admin/lender/field-agent roles (`scripts/grant_role.py`) since those can't be self-registered
by design.

## Project layout

```
src/agrotrust/
  shared/          money, geo, state machines, clock, errors - the shared kernel
  db/              schema.sql, SQLite triggers, connection/transaction handling
  security/        passwords, JWT, permissions, rate limiting
  modules/         one folder per business domain (identity, marketplace, orders,
                   escrow, ledger, payments, farms, traceability, inventory,
                   logistics, lending, insurance, offline_sync, analytics, ml, admin, ...)
  api/             Flask app (container.py wires everything together, app.py has the routes)
  observability/   structured logging + in-memory metrics
  workers/         DB-backed background job queue
  events/          transactional outbox + in-process event bus
tests/
  unit/            shared kernel tests
  integration/     one file per module, real SQLite files, real concurrency tests
  api/             end-to-end HTTP tests via Flask's test client
docs/
  adr/             architecture decision records
  FINAL_EVALUATION.md
migrations/
  postgres_extras.sql   the PostGIS/trigger-function additions for a real Postgres deployment
docker/, .github/workflows/   authored but untested in this sandbox (no Docker/CI runner here)
```

## Opening in VS Code

1. Unzip and open the `agrotrust/` folder as your workspace root.
2. Point VS Code's Python interpreter at a 3.12 virtualenv (Command Palette → "Python: Select
   Interpreter").
3. If you want the test explorer to discover tests, set `python.testing.unittestArgs` to
   `["-s", "tests", "-p", "test_*.py"]` and `python.testing.unittestEnabled` to `true` in
   `.vscode/settings.json`, or just install pytest and use the pytest test explorer instead —
   both work since every test file follows standard conventions.
4. Set `PYTHONPATH=src` (a `.env` file with `PYTHONPATH=src` in the workspace root is the
   easiest way — VS Code picks it up automatically for both the terminal and the debugger).
