-- PostgreSQL-only additions on top of schema.sql, for a real production deployment.
-- NOT executed or tested in this sandbox (no PostgreSQL server available) - written and
-- reviewed against the PostgreSQL 15 + PostGIS 3 documentation, applied here as the intended
-- migration path referenced by docs/adr/ADR-002. Apply after running schema.sql's statements
-- through a PostgreSQL-compatible migration tool (Alembic, in the originally-specified stack).

-- 1. PostGIS geography columns + GiST spatial indexes, replacing the lat/lon + haversine
--    bounding-box-prefilter pattern used in shared/geo.py for the SQLite build.
CREATE EXTENSION IF NOT EXISTS postgis;

ALTER TABLE farms ADD COLUMN IF NOT EXISTS location geography(Point, 4326);
UPDATE farms SET location = ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography WHERE lat IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_farms_location_gist ON farms USING GIST (location);

ALTER TABLE farms ADD COLUMN IF NOT EXISTS boundary geography(Polygon, 4326);
-- boundary_geojson (TEXT) is populated by the application; a one-time backfill would run:
--   UPDATE farms SET boundary = ST_SetSRID(ST_GeomFromGeoJSON(boundary_geojson), 4326)::geography
--   WHERE boundary_geojson IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_farms_boundary_gist ON farms USING GIST (boundary);

ALTER TABLE listings ADD COLUMN IF NOT EXISTS location geography(Point, 4326);
UPDATE listings SET location = ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography WHERE lat IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_listings_location_gist ON listings USING GIST (location);

-- application query pattern becomes (replacing shared/geo.bbox_for_radius + haversine filter):
--   SELECT * FROM listings WHERE ST_DWithin(location, ST_MakePoint(:lon,:lat)::geography, :radius_m);

-- 2. Full-text search: PostgreSQL tsvector/GIN, replacing SQLite FTS5's listings_fts virtual
--    table + sync triggers (db/database.py, db/schema.sql).
ALTER TABLE listings ADD COLUMN IF NOT EXISTS search_vector tsvector
  GENERATED ALWAYS AS (to_tsvector('english', coalesce(title,'') || ' ' || coalesce(description,''))) STORED;
CREATE INDEX IF NOT EXISTS ix_listings_search_gin ON listings USING GIN (search_vector);
-- application query pattern: WHERE search_vector @@ websearch_to_tsquery('english', :q)

-- 3. Immutability: PostgreSQL trigger functions, replacing SQLite's inline
--    "BEFORE UPDATE/DELETE ... RAISE(ABORT)" triggers (db/triggers_sqlite.sql).
CREATE OR REPLACE FUNCTION reject_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION '% rows are immutable (attempted % on id=%)', TG_TABLE_NAME, TG_OP, OLD.id;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['audit_log', 'journal_entries', 'journal_lines', 'custody_events',
                           'credit_assessments', 'inventory_movements', 'state_transitions']
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS %I_no_update ON %I', t, t);
    EXECUTE format('DROP TRIGGER IF EXISTS %I_no_delete ON %I', t, t);
    EXECUTE format('CREATE TRIGGER %I_no_update BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION reject_mutation()', t, t);
    EXECUTE format('CREATE TRIGGER %I_no_delete BEFORE DELETE ON %I FOR EACH ROW EXECUTE FUNCTION reject_mutation()', t, t);
  END LOOP;
END $$;
-- Equally valid, simpler alternative: REVOKE UPDATE, DELETE ON these tables FROM the
-- application's runtime role entirely, and grant a separate, rarely-used "dba" role for the
-- exceptional/manual correction case. Triggers are used here to match the SQLite build's
-- behavior (an explicit exception naming the violation) rather than a silent permission denial.

-- 4. Deferred CHECK constraint for the ledger balance invariant: SQLite enforces
--    "debit == credit" per statement (checked in application code before insert, re-verified by
--    LedgerService.trial_balance()); PostgreSQL can enforce it declaratively as a deferred
--    constraint trigger that runs once at COMMIT, after all of a multi-line entry's rows exist.
CREATE OR REPLACE FUNCTION check_journal_entry_balance() RETURNS trigger AS $$
DECLARE
  debit_total BIGINT;
  credit_total BIGINT;
BEGIN
  SELECT COALESCE(SUM(CASE WHEN side='D' THEN amount_minor ELSE 0 END),0),
         COALESCE(SUM(CASE WHEN side='C' THEN amount_minor ELSE 0 END),0)
    INTO debit_total, credit_total
    FROM journal_lines WHERE entry_id = NEW.entry_id;
  IF debit_total != credit_total THEN
    RAISE EXCEPTION 'journal entry % is unbalanced: debits=% credits=%', NEW.entry_id, debit_total, credit_total;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_journal_lines_balance_check ON journal_lines;
CREATE CONSTRAINT TRIGGER trg_journal_lines_balance_check
  AFTER INSERT ON journal_lines
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION check_journal_entry_balance();

-- 5. Concurrency: SQLite's BEGIN IMMEDIATE takes a write lock upfront to serialize
--    read-check-write sequences (db/database.py). PostgreSQL's MVCC allows the equivalent
--    behavior via SELECT ... FOR UPDATE on the specific row(s) being checked-and-updated
--    (e.g. an account balance check before an overdraft-guarded post), which permits far more
--    concurrent throughput for unrelated rows. No schema change needed for this - it is a
--    change to the query pattern in ledger/service.py's post() method, from "whole-database
--    write lock" to "row-level lock on the specific ledger_accounts rows touched by this entry".
