// Shapes returned by the real AgroTrust backend. Kept intentionally close to
// what src/agrotrust/api/app.py actually serializes, not an idealized version
// of it, so a response mismatch is a backend bug, not a frontend assumption.

export type Role =
  | "FARMER"
  | "COOPERATIVE_ADMIN"
  | "AGGREGATOR"
  | "BUYER"
  | "LENDER"
  | "FIELD_AGENT"
  | "LOGISTICS_PROVIDER"
  | "INSURER"
  | "PLATFORM_ADMIN";

export interface User {
  id: string;
  phone: string;
  email: string | null;
  full_name: string;
  roles: Role[];
  created_at: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: "Bearer";
  expires_in: number;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
}

export type ListingStatus = "ACTIVE" | "PAUSED" | "SOLD_OUT" | "CLOSED";

// Mirrors the `listings` table (db/schema.sql) plus the two derived string
// fields the service layer adds in _present(): quantity_available and price
// are formatted decimal strings, not the raw *_minor / *_milli integers.
export interface Listing {
  id: string;
  seller_id: string;
  org_id: string | null;
  farm_id: string | null;
  crop_id: string;
  title: string;
  description: string;
  quantity_total_milli: number;
  quantity_available_milli: number;
  quantity_available: string;
  unit: string;
  price_minor: number;
  price: string;
  currency: string;
  state: string;
  lga: string;
  lat: number | null;
  lon: number | null;
  quality_grade: "A" | "B" | "C" | "UNGRADED";
  status: ListingStatus;
  farm_verified: 0 | 1;
  created_at: string;
  updated_at: string;
}

export interface ListingSearchResult {
  total: number;
  items: Listing[];
}

// Mirrors the `orders` table CHECK constraint exactly, including IN_TRANSIT
// (not "DISPATCHED" - the dispatch action transitions the order into this
// state, but the state value itself is IN_TRANSIT).
export type OrderState =
  | "CREATED"
  | "CONFIRMED"
  | "FUNDED"
  | "PREPARING"
  | "IN_TRANSIT"
  | "DELIVERY_FAILED"
  | "DELIVERED"
  | "INSPECTED"
  | "DISPUTED"
  | "COMPLETED"
  | "CANCELLED";

export interface Order {
  id: string;
  buyer_id: string;
  seller_id: string;
  listing_id: string | null;
  crop_id: string;
  qty_milli: number;
  delivered_qty_milli: number | null;
  accepted_qty_milli: number | null;
  unit: string;
  unit_price_minor: number;
  total_minor: number;
  currency: string;
  state: OrderState;
  delivery_address: string | null;
  quality_result: string | null;
  cancel_reason: string | null;
  created_at: string;
  updated_at: string;
}

export type EscrowState =
  | "CREATED"
  | "FUNDED"
  | "IN_TRANSIT"
  | "DELIVERED"
  | "INSPECTED"
  | "DISPUTED"
  | "RESOLVED"
  | "RELEASED"
  | "REFUNDED"
  | "CANCELLED";

// Mirrors the `escrows` table. amount_minor is the full amount held; on
// release it splits into seller_minor (paid out) and fee_minor (platform
// cut), both starting at 0 until release actually happens.
export interface EscrowSnapshot {
  id: string;
  order_id: string;
  buyer_id: string;
  seller_id: string;
  amount_minor: number;
  seller_minor: number;
  fee_minor: number;
  refunded_minor: number;
  currency: string;
  state: EscrowState;
  created_at: string;
  updated_at: string;
}

export type FarmVerificationStatus =
  | "UNVERIFIED"
  | "PENDING"
  | "ASSIGNED"
  | "VISITED"
  | "SUBMITTED"
  | "UNDER_REVIEW"
  | "VERIFIED"
  | "REJECTED";

export interface Farm {
  id: string;
  owner_user_id: string;
  org_id: string | null;
  name: string;
  state: string;
  lga: string;
  community: string | null;
  size_hectares: number;
  lat: number;
  lon: number;
  verification_status: FarmVerificationStatus;
  verified_at: string | null;
  assigned_agent_id: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface Organization {
  id: string;
  name: string;
  type: string;
  created_at: string;
}

// Mirrors the `vehicles` / `drivers` / `shipments` / `delivery_events` tables
// (db/schema.sql). Shipments use the same optimistic-concurrency `version`
// field pattern as orders, and delivery_events are milestone-only (no
// continuous GPS stream): lat/lon are only set on PICKED_UP and DELIVERED,
// null everywhere else, by deliberate data-minimization design.
export interface Vehicle {
  id: string;
  org_id: string;
  plate: string;
  vehicle_type: string;
  capacity_kg: number;
  active: 0 | 1;
}

export interface Driver {
  id: string;
  org_id: string;
  user_id: string | null;
  name: string;
  phone: string;
  active: 0 | 1;
}

export type ShipmentState = "CREATED" | "ASSIGNED" | "PICKED_UP" | "IN_TRANSIT" | "DELIVERED" | "CONFIRMED" | "FAILED";

export interface Shipment {
  id: string;
  order_id: string;
  provider_org_id: string | null;
  driver_id: string | null;
  vehicle_id: string | null;
  state: ShipmentState;
  pickup_lat: number | null;
  pickup_lon: number | null;
  dropoff_lat: number | null;
  dropoff_lon: number | null;
  scheduled_pickup: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface DeliveryEvent {
  id: number;
  shipment_id: string;
  event_type: string;
  lat: number | null;
  lon: number | null;
  note: string | null;
  actor_id: string | null;
  at: string;
}

export interface Notification {
  id: string;
  user_id: string;
  title: string;
  body: string;
  read_at: string | null;
  created_at: string;
}

export interface FarmerAnalytics {
  farms_total: number;
  farms_verified: number;
  completed_sales: number;
  sales_revenue_minor: number;
  active_listings: number;
  active_loans: number;
  active_loan_principal_minor: number;
}

export interface BuyerAnalytics {
  orders_total: number;
  orders_completed: number;
  orders_disputed: number;
  total_spend_minor: number;
}

export interface PlatformAnalytics {
  active_users: number;
  farms_total: number;
  farms_verified: number;
  gross_merchandise_value_minor: number;
  platform_fee_revenue_minor: number;
  open_disputes: number;
}

export interface Paginated<T> {
  items: T[];
  next_cursor?: string | null;
}

// --------------------------------------------------------------- lending
// Mirrors `loan_products` / `loan_applications` / `loans` /
// `repayment_schedule` / `credit_assessments` (db/schema.sql).
export interface LoanProduct {
  id: string;
  lender_org_id: string;
  name: string;
  min_amount_minor: number;
  max_amount_minor: number;
  min_term_months: number;
  max_term_months: number;
  annual_rate_bps: number;
  late_fee_bps: number;
  min_credit_score: number;
  requires_verified_farm: 0 | 1;
  active: 0 | 1;
  created_at: string;
}

export type LoanApplicationState = "APPLICATION" | "ASSESSMENT" | "APPROVED" | "REJECTED" | "DISBURSED" | "CANCELLED";

export interface LoanApplication {
  id: string;
  applicant_id: string;
  product_id: string;
  amount_minor: number;
  term_months: number;
  purpose: string | null;
  state: LoanApplicationState;
  credit_assessment_id: string | null;
  decided_by: string | null;
  decision_reason: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export type LoanState = "DISBURSED" | "ACTIVE" | "REPAYING" | "COMPLETED" | "DEFAULTED";

export interface Loan {
  id: string;
  application_id: string;
  borrower_id: string;
  product_id: string;
  lender_org_id: string;
  principal_minor: number;
  term_months: number;
  annual_rate_bps: number;
  late_fee_bps: number;
  state: LoanState;
  schedule_version: number;
  disbursed_at: string;
  version: number;
  updated_at: string;
}

export interface RepaymentInstallment {
  id: string;
  loan_id: string;
  schedule_version: number;
  installment_no: number;
  due_date: string;
  principal_due_minor: number;
  interest_due_minor: number;
  principal_paid_minor: number;
  interest_paid_minor: number;
  penalty_minor: number;
  penalty_paid_minor: number;
  status: "PENDING" | "PARTIAL" | "PAID" | "OVERDUE" | "SUPERSEDED";
  paid_at: string | null;
}

export interface CreditAssessment {
  id: string;
  user_id: string;
  application_id: string | null;
  score: number;
  risk_grade: "A" | "B" | "C" | "D" | "E";
  factors: string;
  features: string;
  model_version: string;
  generated_at: string;
}

// -------------------------------------------------------------- insurance
// Mirrors `insurance_policies` (db/schema.sql).
export type InsurancePolicyState = "PENDING_PAYMENT" | "ACTIVE" | "TRIGGERED" | "EXPIRED" | "CANCELLED";

export interface InsurancePolicy {
  id: string;
  farm_id: string;
  holder_id: string;
  insurer_org_id: string | null;
  coverage_minor: number;
  premium_minor: number;
  trigger_type: string;
  trigger_config: string;
  window_start: string;
  window_end: string;
  station_lat: number | null;
  station_lon: number | null;
  state: InsurancePolicyState;
  premium_paid_at: string | null;
  provider_policy_ref: string | null;
  created_at: string;
}

// ----------------------------------------------------------- traceability
// Mirrors `lots` / `custody_events` / `weighing_records` / `quality_inspections`.
export interface Lot {
  id: string;
  code: string;
  farm_id: string;
  crop_id: string;
  owner_user_id: string;
  quantity_milli: number;
  unit: string;
  harvest_date: string;
  quality_grade: "A" | "B" | "C" | "REJECT" | "UNGRADED";
  created_at: string;
}

export interface CustodyEvent {
  id: number;
  lot_id: string;
  event_type: "HARVESTED" | "AGGREGATED" | "WAREHOUSED" | "DISPATCHED" | "IN_TRANSIT" | "DELIVERED" | "INSPECTED" | "SPLIT" | "RETURNED";
  from_party: string | null;
  to_party: string | null;
  location_label: string | null;
  lat: number | null;
  lon: number | null;
  weight_milli: number | null;
  reference_type: string | null;
  reference_id: string | null;
  note: string | null;
  actor_id: string;
  at: string;
}

export interface WeighingRecord {
  id: string;
  lot_id: string;
  warehouse_id: string | null;
  gross_milli: number;
  tare_milli: number;
  net_milli: number;
  actor_id: string;
  at: string;
}

export interface QualityInspection {
  id: string;
  lot_id: string;
  inspector_id: string;
  grade: "A" | "B" | "C" | "REJECT";
  moisture_pct: number | null;
  defects_pct: number | null;
  passed: 0 | 1;
  notes: string | null;
  at: string;
}

// -------------------------------------------------------------------- admin
// Mirrors the shapes AdminService composes, not a raw table.
export interface AdminUserSummary {
  id: string;
  phone: string;
  email: string | null;
  full_name: string | null;
  status: "PENDING" | "ACTIVE" | "SUSPENDED" | "DELETED";
  created_at: string;
}

export interface AdminUserDetail extends AdminUserSummary {
  roles: Role[];
  organizations: { org_id: string; role: string }[];
  kyc: { status: string; updated_at: string } | null;
}

export interface AuditLogEntry {
  id: number;
  at: string;
  actor_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  old_state: string | null;
  new_state: string | null;
  context: string | null;
}

export type DisputeState = "OPEN" | "RESOLVED";

export interface Dispute {
  id: string;
  order_id: string;
  escrow_id: string | null;
  opened_by: string;
  reason: string;
  state: DisputeState;
  resolution: string | null;
  seller_amount_minor: number | null;
  buyer_amount_minor: number | null;
  resolved_by: string | null;
  opened_at: string;
  resolved_at: string | null;
}
