-- AgroTrust portable schema (SQLite for dev/test, PostgreSQL for production).
-- Conventions:
--   * ids are UUID strings (TEXT); timestamps are fixed-width UTC ISO-8601 TEXT
--     (lexicographic order == chronological order) so one schema serves both engines.
--   * money is INTEGER minor units (kobo); quantities are INTEGER milli-units.
--   * booleans are INTEGER 0/1 with CHECKs.
--   * PostgreSQL-only extras (PostGIS, immutability triggers, deferred balance
--     constraint) live in migrations/postgres_extras.sql.

-- ------------------------------------------------------------------ identity
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  phone TEXT NOT NULL UNIQUE,
  email TEXT UNIQUE,
  password_hash TEXT NOT NULL,
  full_name TEXT,
  status TEXT NOT NULL CHECK (status IN ('PENDING','ACTIVE','SUSPENDED','DELETED')),
  phone_verified INTEGER NOT NULL DEFAULT 0 CHECK (phone_verified IN (0,1)),
  failed_logins INTEGER NOT NULL DEFAULT 0,
  locked_until TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS roles (
  name TEXT PRIMARY KEY,
  description TEXT,
  self_register INTEGER NOT NULL DEFAULT 0 CHECK (self_register IN (0,1))
);
CREATE TABLE IF NOT EXISTS role_permissions (
  role TEXT NOT NULL REFERENCES roles(name),
  permission TEXT NOT NULL,
  PRIMARY KEY (role, permission)
);
CREATE TABLE IF NOT EXISTS user_roles (
  user_id TEXT NOT NULL REFERENCES users(id),
  role TEXT NOT NULL REFERENCES roles(name),
  granted_by TEXT,
  granted_at TEXT NOT NULL,
  PRIMARY KEY (user_id, role)
);
CREATE TABLE IF NOT EXISTS refresh_tokens (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  family_id TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,   -- only the SHA-256 of the token is stored
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT,
  revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_refresh_family ON refresh_tokens(family_id);  -- family revocation on reuse
CREATE INDEX IF NOT EXISTS ix_refresh_user ON refresh_tokens(user_id);
CREATE TABLE IF NOT EXISTS otp_codes (
  id TEXT PRIMARY KEY,
  phone TEXT NOT NULL,
  purpose TEXT NOT NULL,
  code_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  consumed_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_otp_lookup ON otp_codes(phone, purpose, created_at);
CREATE TABLE IF NOT EXISTS kyc_records (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  id_type TEXT NOT NULL,
  id_last4 TEXT NOT NULL,             -- data minimisation: never the full ID number
  provider TEXT NOT NULL,
  provider_reference TEXT,
  status TEXT NOT NULL CHECK (status IN ('PENDING','VERIFIED','FAILED')),
  classification TEXT NOT NULL DEFAULT 'HIGHLY_SENSITIVE',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_kyc_user ON kyc_records(user_id);

CREATE TABLE IF NOT EXISTS organizations (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('COOPERATIVE','LENDER','NGO','BUYER','AGGREGATOR','LOGISTICS','INSURER','PROCESSOR','OTHER')),
  status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','SUSPENDED')),
  state TEXT, lga TEXT,
  lat DOUBLE PRECISION, lon DOUBLE PRECISION,
  created_by TEXT NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_org_type ON organizations(type, status);
CREATE TABLE IF NOT EXISTS org_members (
  org_id TEXT NOT NULL REFERENCES organizations(id),
  user_id TEXT NOT NULL REFERENCES users(id),
  org_role TEXT NOT NULL CHECK (org_role IN ('ADMIN','STAFF','MEMBER')),
  created_at TEXT NOT NULL,
  PRIMARY KEY (org_id, user_id)
);
CREATE INDEX IF NOT EXISTS ix_org_members_user ON org_members(user_id);

CREATE TABLE IF NOT EXISTS files (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL REFERENCES users(id),
  storage_key TEXT NOT NULL UNIQUE,
  filename TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
  sha256 TEXT NOT NULL,
  classification TEXT NOT NULL DEFAULT 'INTERNAL' CHECK (classification IN ('PUBLIC','INTERNAL','CONFIDENTIAL','HIGHLY_SENSITIVE')),
  created_at TEXT NOT NULL
);

-- --------------------------------------------------------------- farm registry
CREATE TABLE IF NOT EXISTS crops (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  default_unit TEXT NOT NULL DEFAULT 'KG',
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1))
);
CREATE TABLE IF NOT EXISTS farms (
  id TEXT PRIMARY KEY,
  owner_user_id TEXT NOT NULL REFERENCES users(id),
  org_id TEXT REFERENCES organizations(id),
  name TEXT NOT NULL,
  state TEXT NOT NULL, lga TEXT NOT NULL, community TEXT,
  size_hectares DOUBLE PRECISION NOT NULL CHECK (size_hectares > 0),
  lat DOUBLE PRECISION NOT NULL CHECK (lat BETWEEN -90 AND 90),
  lon DOUBLE PRECISION NOT NULL CHECK (lon BETWEEN -180 AND 180),
  boundary_geojson TEXT,               -- PostGIS geography(Polygon) mirror in postgres_extras.sql
  verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED'
     CHECK (verification_status IN ('UNVERIFIED','PENDING','ASSIGNED','VISITED','SUBMITTED','UNDER_REVIEW','VERIFIED','REJECTED')),
  verified_at TEXT,
  assigned_agent_id TEXT REFERENCES users(id),
  notes TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_farms_owner ON farms(owner_user_id);
CREATE INDEX IF NOT EXISTS ix_farms_region ON farms(state, lga);                  -- LGA / state filters
CREATE INDEX IF NOT EXISTS ix_farms_latlon ON farms(lat, lon);                    -- bounding-box prefilter for radius search
CREATE INDEX IF NOT EXISTS ix_farms_agent ON farms(assigned_agent_id, verification_status)
  WHERE assigned_agent_id IS NOT NULL;                                           -- agent work-queue
CREATE TABLE IF NOT EXISTS farm_crops (
  farm_id TEXT NOT NULL REFERENCES farms(id),
  crop_id TEXT NOT NULL REFERENCES crops(id),
  PRIMARY KEY (farm_id, crop_id)
);
CREATE TABLE IF NOT EXISTS farm_visits (
  id TEXT PRIMARY KEY,
  farm_id TEXT NOT NULL REFERENCES farms(id),
  agent_id TEXT NOT NULL REFERENCES users(id),
  client_id TEXT NOT NULL,             -- offline-generated id -> idempotent sync
  lat DOUBLE PRECISION NOT NULL, lon DOUBLE PRECISION NOT NULL,
  distance_m DOUBLE PRECISION NOT NULL,
  observations TEXT,
  visited_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (agent_id, client_id)
);
CREATE INDEX IF NOT EXISTS ix_visits_farm ON farm_visits(farm_id);
CREATE TABLE IF NOT EXISTS farm_files (
  farm_id TEXT NOT NULL REFERENCES farms(id),
  file_id TEXT NOT NULL REFERENCES files(id),
  kind TEXT NOT NULL DEFAULT 'PHOTO',
  PRIMARY KEY (farm_id, file_id)
);
CREATE TABLE IF NOT EXISTS state_transitions (
  id {{AUTO_PK}},
  entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
  from_state TEXT, to_state TEXT NOT NULL,
  actor_id TEXT, reason TEXT,
  at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_transitions_entity ON state_transitions(entity_type, entity_id);

-- ------------------------------------------------------------------ marketplace
CREATE TABLE IF NOT EXISTS listings (
  id TEXT PRIMARY KEY,
  seller_id TEXT NOT NULL REFERENCES users(id),
  org_id TEXT REFERENCES organizations(id),
  farm_id TEXT REFERENCES farms(id),
  crop_id TEXT NOT NULL REFERENCES crops(id),
  title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
  quantity_total_milli BIGINT NOT NULL CHECK (quantity_total_milli > 0),
  quantity_available_milli BIGINT NOT NULL,
  unit TEXT NOT NULL,
  price_minor BIGINT NOT NULL CHECK (price_minor > 0),   -- price per unit
  currency TEXT NOT NULL DEFAULT 'NGN',
  state TEXT NOT NULL, lga TEXT NOT NULL,
  lat DOUBLE PRECISION, lon DOUBLE PRECISION,
  quality_grade TEXT NOT NULL DEFAULT 'UNGRADED' CHECK (quality_grade IN ('A','B','C','UNGRADED')),
  harvest_start TEXT, harvest_end TEXT,
  status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','PAUSED','SOLD_OUT','CLOSED')),
  farm_verified INTEGER NOT NULL DEFAULT 0 CHECK (farm_verified IN (0,1)),
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  CHECK (quantity_available_milli >= 0 AND quantity_available_milli <= quantity_total_milli)  -- oversell guard
);
CREATE INDEX IF NOT EXISTS ix_listings_browse ON listings(crop_id, status, price_minor) WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS ix_listings_region ON listings(state, lga);
CREATE INDEX IF NOT EXISTS ix_listings_seller ON listings(seller_id);
CREATE TABLE IF NOT EXISTS listing_files (
  listing_id TEXT NOT NULL REFERENCES listings(id),
  file_id TEXT NOT NULL REFERENCES files(id),
  PRIMARY KEY (listing_id, file_id)
);

-- ------------------------------------------------------------- contracts, orders
CREATE TABLE IF NOT EXISTS contracts (
  id TEXT PRIMARY KEY,
  buyer_id TEXT NOT NULL REFERENCES users(id),
  seller_id TEXT NOT NULL REFERENCES users(id),
  seller_org_id TEXT REFERENCES organizations(id),
  crop_id TEXT NOT NULL REFERENCES crops(id),
  expected_qty_milli BIGINT NOT NULL CHECK (expected_qty_milli > 0),
  fulfilled_qty_milli BIGINT NOT NULL DEFAULT 0,
  unit TEXT NOT NULL,
  price_minor BIGINT NOT NULL CHECK (price_minor > 0),
  quality_requirements TEXT,
  delivery_start TEXT NOT NULL, delivery_end TEXT NOT NULL,
  delivery_location TEXT NOT NULL,
  payment_terms TEXT,
  state TEXT NOT NULL CHECK (state IN ('DRAFT','PROPOSED','ACCEPTED','ACTIVE','FULFILLING','COMPLETED','CANCELLED','REJECTED')),
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  CHECK (delivery_end >= delivery_start)
);
CREATE INDEX IF NOT EXISTS ix_contracts_buyer ON contracts(buyer_id, state);
CREATE INDEX IF NOT EXISTS ix_contracts_seller ON contracts(seller_id, state);
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,
  buyer_id TEXT NOT NULL REFERENCES users(id),
  seller_id TEXT NOT NULL REFERENCES users(id),
  listing_id TEXT REFERENCES listings(id),
  contract_id TEXT REFERENCES contracts(id),
  crop_id TEXT NOT NULL REFERENCES crops(id),
  qty_milli BIGINT NOT NULL CHECK (qty_milli > 0),
  delivered_qty_milli BIGINT,
  accepted_qty_milli BIGINT,
  unit TEXT NOT NULL,
  unit_price_minor BIGINT NOT NULL CHECK (unit_price_minor > 0),
  total_minor BIGINT NOT NULL CHECK (total_minor > 0),
  currency TEXT NOT NULL DEFAULT 'NGN',
  state TEXT NOT NULL CHECK (state IN ('CREATED','CONFIRMED','FUNDED','PREPARING','IN_TRANSIT','DELIVERY_FAILED','DELIVERED','INSPECTED','DISPUTED','COMPLETED','CANCELLED')),
  delivery_address TEXT,
  quality_result TEXT,
  cancel_reason TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  CHECK (delivered_qty_milli IS NULL OR delivered_qty_milli >= 0),
  CHECK (accepted_qty_milli IS NULL OR (accepted_qty_milli >= 0 AND delivered_qty_milli IS NOT NULL AND accepted_qty_milli <= delivered_qty_milli))
);
CREATE INDEX IF NOT EXISTS ix_orders_buyer ON orders(buyer_id, state);
CREATE INDEX IF NOT EXISTS ix_orders_seller ON orders(seller_id, state);
CREATE INDEX IF NOT EXISTS ix_orders_listing ON orders(listing_id);
CREATE TABLE IF NOT EXISTS disputes (
  id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL REFERENCES orders(id),
  escrow_id TEXT,
  opened_by TEXT NOT NULL REFERENCES users(id),
  reason TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('OPEN','RESOLVED')),
  resolution TEXT,
  seller_amount_minor BIGINT, buyer_amount_minor BIGINT,
  resolved_by TEXT,
  opened_at TEXT NOT NULL, resolved_at TEXT
);
-- at most one open dispute per order
CREATE UNIQUE INDEX IF NOT EXISTS ux_disputes_open ON disputes(order_id) WHERE state = 'OPEN';

-- ------------------------------------------------------------- escrow and ledger
CREATE TABLE IF NOT EXISTS escrows (
  id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL UNIQUE REFERENCES orders(id),
  buyer_id TEXT NOT NULL REFERENCES users(id),
  seller_id TEXT NOT NULL REFERENCES users(id),
  amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
  seller_minor BIGINT NOT NULL DEFAULT 0,
  fee_minor BIGINT NOT NULL DEFAULT 0,
  refunded_minor BIGINT NOT NULL DEFAULT 0,
  currency TEXT NOT NULL DEFAULT 'NGN',
  state TEXT NOT NULL CHECK (state IN ('CREATED','FUNDED','IN_TRANSIT','DELIVERED','INSPECTED','DISPUTED','RESOLVED','RELEASED','REFUNDED','CANCELLED')),
  funded_payment_id TEXT,
  pending_seller_minor BIGINT, pending_fee_minor BIGINT, pending_refund_minor BIGINT,  -- computed split awaiting release
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  CHECK (seller_minor >= 0 AND fee_minor >= 0 AND refunded_minor >= 0),
  CHECK (seller_minor + fee_minor + refunded_minor <= amount_minor)  -- can never pay out more than was held
);
CREATE TABLE IF NOT EXISTS ledger_accounts (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('ASSET','LIABILITY','EQUITY','REVENUE','EXPENSE')),
  owner_user_id TEXT REFERENCES users(id),
  currency TEXT NOT NULL DEFAULT 'NGN',
  allow_negative INTEGER NOT NULL DEFAULT 0 CHECK (allow_negative IN (0,1)),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ledger_accounts_owner ON ledger_accounts(owner_user_id);
CREATE TABLE IF NOT EXISTS journal_entries (
  id TEXT PRIMARY KEY,
  reference TEXT NOT NULL UNIQUE,      -- natural idempotency key for financial effects
  entry_type TEXT NOT NULL,
  description TEXT NOT NULL,
  total_debit_minor BIGINT NOT NULL,
  total_credit_minor BIGINT NOT NULL,
  reverses_entry_id TEXT UNIQUE REFERENCES journal_entries(id),  -- an entry can be reversed at most once
  meta TEXT,
  created_by TEXT,
  created_at TEXT NOT NULL,
  CHECK (total_debit_minor = total_credit_minor AND total_debit_minor > 0)
);
CREATE TABLE IF NOT EXISTS journal_lines (
  id {{AUTO_PK}},
  entry_id TEXT NOT NULL REFERENCES journal_entries(id),
  account_id TEXT NOT NULL REFERENCES ledger_accounts(id),
  side TEXT NOT NULL CHECK (side IN ('D','C')),
  amount_minor BIGINT NOT NULL CHECK (amount_minor > 0)
);
CREATE INDEX IF NOT EXISTS ix_lines_account ON journal_lines(account_id);   -- balance = SUM over account
CREATE INDEX IF NOT EXISTS ix_lines_entry ON journal_lines(entry_id);

-- ---------------------------------------------------------------------- payments
CREATE TABLE IF NOT EXISTS payments (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('CHARGE','PAYOUT','REFUND')),
  order_id TEXT REFERENCES orders(id),
  user_id TEXT NOT NULL REFERENCES users(id),
  provider TEXT NOT NULL,
  reference TEXT NOT NULL UNIQUE,      -- our merchant reference, sent to the provider
  provider_reference TEXT,
  amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
  currency TEXT NOT NULL DEFAULT 'NGN',
  status TEXT NOT NULL CHECK (status IN ('PENDING','SUCCEEDED','FAILED','REVERSED')),
  checkout_url TEXT, failure_reason TEXT, meta TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_payments_order ON payments(order_id);
CREATE INDEX IF NOT EXISTS ix_payments_user ON payments(user_id, kind);
CREATE TABLE IF NOT EXISTS webhook_events (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  event_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload TEXT NOT NULL,
  signature_valid INTEGER NOT NULL CHECK (signature_valid IN (0,1)),
  status TEXT NOT NULL CHECK (status IN ('RECEIVED','PROCESSED','FAILED','IGNORED')),
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  received_at TEXT NOT NULL, processed_at TEXT,
  UNIQUE (provider, event_id)          -- duplicate deliveries collapse here
);
CREATE TABLE IF NOT EXISTS idempotency_keys (
  scope TEXT NOT NULL,                 -- user id / client id
  key TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('IN_PROGRESS','COMPLETED')),
  status_code INTEGER,
  response TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY (scope, key)
);

-- ------------------------------------------------------ events, jobs, audit
CREATE TABLE IF NOT EXISTS outbox (
  id {{AUTO_PK}},
  event_id TEXT NOT NULL UNIQUE,
  event_type TEXT NOT NULL,
  aggregate_type TEXT NOT NULL, aggregate_id TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL,
  published_at TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT
);
CREATE INDEX IF NOT EXISTS ix_outbox_pending ON outbox(id) WHERE published_at IS NULL;  -- publisher scan
CREATE TABLE IF NOT EXISTS processed_events (
  handler TEXT NOT NULL, event_id TEXT NOT NULL, processed_at TEXT NOT NULL,
  PRIMARY KEY (handler, event_id)      -- consumer-side de-duplication (at-least-once delivery)
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  payload TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('PENDING','RUNNING','DONE','FAILED')),
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  run_at TEXT NOT NULL,
  last_error TEXT,
  dedupe_key TEXT UNIQUE,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_jobs_due ON jobs(run_at) WHERE status = 'PENDING';
CREATE TABLE IF NOT EXISTS audit_log (
  id {{AUTO_PK}},
  at TEXT NOT NULL,
  actor_id TEXT,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL, resource_id TEXT,
  old_state TEXT, new_state TEXT,
  context TEXT,
  prev_hash TEXT,
  hash TEXT NOT NULL                    -- SHA-256 chain: tamper-evident
);
CREATE INDEX IF NOT EXISTS ix_audit_resource ON audit_log(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS ix_audit_actor ON audit_log(actor_id, at);
CREATE TABLE IF NOT EXISTS system_config (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_by TEXT, updated_at TEXT NOT NULL
);

-- ------------------------------------------------- traceability and inventory
CREATE TABLE IF NOT EXISTS lots (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,            -- LOT-2026-XXXXXX
  farm_id TEXT NOT NULL REFERENCES farms(id),
  crop_id TEXT NOT NULL REFERENCES crops(id),
  owner_user_id TEXT NOT NULL REFERENCES users(id),
  quantity_milli BIGINT NOT NULL CHECK (quantity_milli > 0),
  unit TEXT NOT NULL,
  harvest_date TEXT NOT NULL,
  quality_grade TEXT NOT NULL DEFAULT 'UNGRADED',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_lots_farm ON lots(farm_id);
CREATE TABLE IF NOT EXISTS custody_events (
  id {{AUTO_PK}},
  lot_id TEXT NOT NULL REFERENCES lots(id),
  event_type TEXT NOT NULL CHECK (event_type IN ('HARVESTED','AGGREGATED','WAREHOUSED','DISPATCHED','IN_TRANSIT','DELIVERED','INSPECTED','SPLIT','RETURNED')),
  from_party TEXT, to_party TEXT,
  location_label TEXT, lat DOUBLE PRECISION, lon DOUBLE PRECISION,
  weight_milli BIGINT,
  reference_type TEXT, reference_id TEXT,
  note TEXT,
  actor_id TEXT NOT NULL,
  at TEXT NOT NULL,
  prev_hash TEXT, hash TEXT NOT NULL    -- per-lot hash chain
);
CREATE INDEX IF NOT EXISTS ix_custody_lot ON custody_events(lot_id, id);
CREATE TABLE IF NOT EXISTS order_lots (
  order_id TEXT NOT NULL REFERENCES orders(id),
  lot_id TEXT NOT NULL REFERENCES lots(id),
  qty_milli BIGINT NOT NULL CHECK (qty_milli > 0),
  PRIMARY KEY (order_id, lot_id)
);
CREATE TABLE IF NOT EXISTS warehouses (
  id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL REFERENCES organizations(id),
  name TEXT NOT NULL, state TEXT, lga TEXT,
  lat DOUBLE PRECISION, lon DOUBLE PRECISION,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inventory_movements (
  id {{AUTO_PK}},
  warehouse_id TEXT NOT NULL REFERENCES warehouses(id),
  lot_id TEXT NOT NULL REFERENCES lots(id),
  movement_type TEXT NOT NULL CHECK (movement_type IN ('RECEIPT','TRANSFER_IN','TRANSFER_OUT','ADJUSTMENT','DISPATCH','RETURN')),
  qty_delta_milli BIGINT NOT NULL CHECK (qty_delta_milli <> 0),
  reason TEXT NOT NULL CHECK (length(reason) > 0),
  reference_type TEXT, reference_id TEXT,
  actor_id TEXT NOT NULL,
  at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_inv_stock ON inventory_movements(warehouse_id, lot_id);  -- stock = SUM(delta)
CREATE TABLE IF NOT EXISTS weighing_records (
  id TEXT PRIMARY KEY,
  lot_id TEXT NOT NULL REFERENCES lots(id),
  warehouse_id TEXT REFERENCES warehouses(id),
  gross_milli BIGINT NOT NULL, tare_milli BIGINT NOT NULL, net_milli BIGINT NOT NULL,
  actor_id TEXT NOT NULL, at TEXT NOT NULL,
  CHECK (gross_milli >= tare_milli AND net_milli = gross_milli - tare_milli)
);
CREATE TABLE IF NOT EXISTS quality_inspections (
  id TEXT PRIMARY KEY,
  lot_id TEXT NOT NULL REFERENCES lots(id),
  inspector_id TEXT NOT NULL REFERENCES users(id),
  grade TEXT NOT NULL CHECK (grade IN ('A','B','C','REJECT')),
  moisture_pct DOUBLE PRECISION, defects_pct DOUBLE PRECISION,
  passed INTEGER NOT NULL CHECK (passed IN (0,1)),
  notes TEXT, at TEXT NOT NULL
);

-- ---------------------------------------------------------------------- logistics
CREATE TABLE IF NOT EXISTS vehicles (
  id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL REFERENCES organizations(id),
  plate TEXT NOT NULL UNIQUE, vehicle_type TEXT NOT NULL,
  capacity_kg INTEGER NOT NULL CHECK (capacity_kg > 0),
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS drivers (
  id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL REFERENCES organizations(id),
  user_id TEXT REFERENCES users(id),
  name TEXT NOT NULL, phone TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS shipments (
  id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL REFERENCES orders(id),
  provider_org_id TEXT REFERENCES organizations(id),
  driver_id TEXT REFERENCES drivers(id),
  vehicle_id TEXT REFERENCES vehicles(id),
  state TEXT NOT NULL CHECK (state IN ('CREATED','ASSIGNED','PICKED_UP','IN_TRANSIT','DELIVERED','CONFIRMED','FAILED')),
  pickup_lat DOUBLE PRECISION, pickup_lon DOUBLE PRECISION,
  dropoff_lat DOUBLE PRECISION, dropoff_lon DOUBLE PRECISION,
  scheduled_pickup TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_shipments_order ON shipments(order_id);
CREATE TABLE IF NOT EXISTS delivery_events (
  id {{AUTO_PK}},
  shipment_id TEXT NOT NULL REFERENCES shipments(id),
  event_type TEXT NOT NULL,
  lat DOUBLE PRECISION, lon DOUBLE PRECISION,   -- only captured at milestones, never continuous tracking
  note TEXT, actor_id TEXT, at TEXT NOT NULL
);

-- ------------------------------------------------------------- lending and credit
CREATE TABLE IF NOT EXISTS loan_products (
  id TEXT PRIMARY KEY,
  lender_org_id TEXT NOT NULL REFERENCES organizations(id),
  name TEXT NOT NULL,
  min_amount_minor BIGINT NOT NULL, max_amount_minor BIGINT NOT NULL,
  min_term_months INTEGER NOT NULL, max_term_months INTEGER NOT NULL,
  annual_rate_bps INTEGER NOT NULL CHECK (annual_rate_bps >= 0),
  late_fee_bps INTEGER NOT NULL DEFAULT 0,
  min_credit_score INTEGER NOT NULL DEFAULT 0,
  requires_verified_farm INTEGER NOT NULL DEFAULT 1,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  CHECK (min_amount_minor > 0 AND max_amount_minor >= min_amount_minor AND max_term_months >= min_term_months)
);
CREATE TABLE IF NOT EXISTS credit_assessments (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  application_id TEXT,
  score INTEGER NOT NULL CHECK (score BETWEEN 300 AND 850),
  risk_grade TEXT NOT NULL CHECK (risk_grade IN ('A','B','C','D','E')),
  factors TEXT NOT NULL,                 -- explainable, per-factor contributions
  features TEXT NOT NULL,
  model_version TEXT NOT NULL,
  generated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_credit_user ON credit_assessments(user_id, generated_at);
CREATE TABLE IF NOT EXISTS loan_applications (
  id TEXT PRIMARY KEY,
  applicant_id TEXT NOT NULL REFERENCES users(id),
  product_id TEXT NOT NULL REFERENCES loan_products(id),
  amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
  term_months INTEGER NOT NULL CHECK (term_months > 0),
  purpose TEXT,
  state TEXT NOT NULL CHECK (state IN ('APPLICATION','ASSESSMENT','APPROVED','REJECTED','DISBURSED','CANCELLED')),
  credit_assessment_id TEXT REFERENCES credit_assessments(id),
  decided_by TEXT, decision_reason TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_loanapps_applicant ON loan_applications(applicant_id);
CREATE INDEX IF NOT EXISTS ix_loanapps_product ON loan_applications(product_id, state);
CREATE TABLE IF NOT EXISTS loans (
  id TEXT PRIMARY KEY,
  application_id TEXT NOT NULL UNIQUE REFERENCES loan_applications(id),
  borrower_id TEXT NOT NULL REFERENCES users(id),
  product_id TEXT NOT NULL REFERENCES loan_products(id),
  lender_org_id TEXT NOT NULL REFERENCES organizations(id),
  principal_minor BIGINT NOT NULL,
  term_months INTEGER NOT NULL,
  annual_rate_bps INTEGER NOT NULL,
  late_fee_bps INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL CHECK (state IN ('DISBURSED','ACTIVE','REPAYING','COMPLETED','DEFAULTED')),
  schedule_version INTEGER NOT NULL DEFAULT 1,
  disbursed_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_loans_borrower ON loans(borrower_id);
CREATE INDEX IF NOT EXISTS ix_loans_lender ON loans(lender_org_id, state);
CREATE TABLE IF NOT EXISTS repayment_schedule (
  id TEXT PRIMARY KEY,
  loan_id TEXT NOT NULL REFERENCES loans(id),
  schedule_version INTEGER NOT NULL,
  installment_no INTEGER NOT NULL,
  due_date TEXT NOT NULL,
  principal_due_minor BIGINT NOT NULL, interest_due_minor BIGINT NOT NULL,
  principal_paid_minor BIGINT NOT NULL DEFAULT 0, interest_paid_minor BIGINT NOT NULL DEFAULT 0,
  penalty_minor BIGINT NOT NULL DEFAULT 0, penalty_paid_minor BIGINT NOT NULL DEFAULT 0,
  status TEXT NOT NULL CHECK (status IN ('PENDING','PARTIAL','PAID','OVERDUE','SUPERSEDED')),
  paid_at TEXT,
  UNIQUE (loan_id, schedule_version, installment_no),
  CHECK (principal_paid_minor <= principal_due_minor AND interest_paid_minor <= interest_due_minor AND penalty_paid_minor <= penalty_minor)
);
CREATE INDEX IF NOT EXISTS ix_sched_due ON repayment_schedule(due_date) WHERE status IN ('PENDING','PARTIAL','OVERDUE');
CREATE TABLE IF NOT EXISTS repayments (
  id TEXT PRIMARY KEY,
  loan_id TEXT NOT NULL REFERENCES loans(id),
  payer_id TEXT NOT NULL REFERENCES users(id),
  amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
  reference TEXT NOT NULL UNIQUE,
  ledger_entry_id TEXT REFERENCES journal_entries(id),
  at TEXT NOT NULL
);

-- ---------------------------------------------------------------------- insurance
CREATE TABLE IF NOT EXISTS insurance_policies (
  id TEXT PRIMARY KEY,
  farm_id TEXT NOT NULL REFERENCES farms(id),
  holder_id TEXT NOT NULL REFERENCES users(id),
  insurer_org_id TEXT REFERENCES organizations(id),
  coverage_minor BIGINT NOT NULL CHECK (coverage_minor > 0),
  premium_minor BIGINT NOT NULL CHECK (premium_minor >= 0),
  trigger_type TEXT NOT NULL,
  trigger_config TEXT NOT NULL,
  window_start TEXT NOT NULL, window_end TEXT NOT NULL,
  station_lat DOUBLE PRECISION, station_lon DOUBLE PRECISION,
  state TEXT NOT NULL CHECK (state IN ('PENDING_PAYMENT','ACTIVE','TRIGGERED','EXPIRED','CANCELLED')),
  premium_paid_at TEXT,
  provider_policy_ref TEXT,
  created_at TEXT NOT NULL,
  CHECK (window_end >= window_start)
);
CREATE TABLE IF NOT EXISTS weather_observations (
  id {{AUTO_PK}},
  station_key TEXT NOT NULL,
  observed_on TEXT NOT NULL,
  rainfall_mm DOUBLE PRECISION NOT NULL CHECK (rainfall_mm >= 0),
  source TEXT NOT NULL,
  UNIQUE (station_key, observed_on, source)
);
CREATE TABLE IF NOT EXISTS insurance_claims (
  id TEXT PRIMARY KEY,
  policy_id TEXT NOT NULL UNIQUE REFERENCES insurance_policies(id),  -- one automatic claim per policy period
  trigger_value DOUBLE PRECISION NOT NULL,
  threshold DOUBLE PRECISION NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('APPROVED','PAID','REJECTED')),
  payout_minor BIGINT NOT NULL,
  created_at TEXT NOT NULL
);

-- ------------------------------------------------------------ notifications, sync, ML
CREATE TABLE IF NOT EXISTS notifications (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  channel TEXT NOT NULL CHECK (channel IN ('SMS','EMAIL','PUSH','WHATSAPP','IN_APP')),
  template TEXT NOT NULL,
  params TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('PENDING','SENT','FAILED')),
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT NOT NULL,
  last_error TEXT,
  rendered TEXT,
  read_at TEXT,
  dedupe_key TEXT UNIQUE,
  created_at TEXT NOT NULL, sent_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_notif_pending ON notifications(next_attempt_at) WHERE status = 'PENDING';
CREATE INDEX IF NOT EXISTS ix_notif_user ON notifications(user_id, created_at);
CREATE TABLE IF NOT EXISTS sync_operations (
  device_id TEXT NOT NULL,
  operation_id TEXT NOT NULL,
  user_id TEXT NOT NULL REFERENCES users(id),
  op_type TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('APPLIED','CONFLICT','REJECTED')),
  result TEXT NOT NULL,
  client_created_at TEXT NOT NULL,
  received_at TEXT NOT NULL,
  PRIMARY KEY (device_id, operation_id)  -- replays return the stored result
);
CREATE TABLE IF NOT EXISTS ml_predictions (
  id TEXT PRIMARY KEY,
  model_name TEXT NOT NULL, model_version TEXT NOT NULL,
  subject_type TEXT NOT NULL, subject_id TEXT NOT NULL,
  input_features TEXT NOT NULL,
  prediction DOUBLE PRECISION NOT NULL,
  confidence DOUBLE PRECISION,
  created_at TEXT NOT NULL
);
