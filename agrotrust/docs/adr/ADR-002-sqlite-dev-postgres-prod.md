# ADR-002: SQLite in this sandbox, PostgreSQL in production

**Status:** Accepted (sandbox constraint, not a long-term choice)

## Context
The spec requires PostgreSQL 15+ with PostGIS. This sandbox has no network access, so `pip
install psycopg`/`sqlalchemy` and no PostgreSQL server are available. Only `sqlite3` (stdlib)
and its FTS5 extension are available and already installed.

## Decision
Build against `sqlite3` directly (no ORM), with `schema.sql` written in a PostgreSQL-portable
subset of SQL, and every SQLite-specific construct isolated and commented:
- `triggers_sqlite.sql` implements immutability (audit_log, journal_entries/lines,
  custody_events, credit_assessments, inventory_movements, state_transitions) via
  `BEFORE UPDATE/DELETE ... RAISE(ABORT)` triggers. PostgreSQL would use `BEFORE UPDATE/DELETE`
  trigger functions with `RAISE EXCEPTION`, or simply `REVOKE UPDATE, DELETE` for a service role
  that never needs them - functionally equivalent, syntactically different.
- FTS5 (`listings_fts` virtual table + sync triggers) replaces PostgreSQL's built-in
  `tsvector`/`GIN` full-text search. The query surface (`fts_query()`, `text_search_clause()`)
  is a thin, swappable layer.
- Geo queries use a hand-rolled bounding-box-prefilter-then-haversine pattern
  (`shared/geo.py`) in place of PostGIS `ST_DWithin`/`GiST` indexes. The *query pattern*
  (cheap indexed prefilter, then an exact check) is the same one PostGIS uses internally, so the
  application code above `shared/geo.py` does not need to change when PostGIS is available -
  only `bbox_for_radius`'s SQL clause becomes a `ST_DWithin` call.
- `migrations/postgres_extras.sql` (see that file) captures the PostgreSQL-only additions:
  PostGIS `geography` columns + GiST indexes, deferred `CHECK` constraints, and trigger
  functions written in `plpgsql`.

## Consequences
- Every module's tests run in seconds with zero external services - a genuine benefit even in
  production (fast, hermetic unit/integration tests against real SQLite files), but SQLite's
  single-writer model (`BEGIN IMMEDIATE`) is a coarser concurrency primitive than PostgreSQL's
  MVCC + row locks / `SELECT ... FOR UPDATE`. The application already writes as if it only has
  that coarser guarantee (short transactions, explicit version/CAS columns for optimistic
  concurrency), so the semantics carry over correctly - PostgreSQL will simply allow more
  concurrent throughput for the same code.
- Moving to production requires: swap `db/database.py`'s connection layer for `psycopg`,
  apply `migrations/postgres_extras.sql`, and point `DATABASE_URL` at a real PostgreSQL+PostGIS
  instance. No application-layer module should need to change.
