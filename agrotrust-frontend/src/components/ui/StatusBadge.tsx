import { Badge } from "./Badge";
import type { DisputeState, InsurancePolicyState, LoanApplicationState, LoanState, OrderState, ShipmentState } from "@/types/api";

const STATE_TONE: Record<OrderState, "neutral" | "success" | "warning" | "danger" | "primary"> = {
  CREATED: "neutral",
  CONFIRMED: "primary",
  FUNDED: "primary",
  PREPARING: "primary",
  IN_TRANSIT: "warning",
  DELIVERED: "warning",
  DELIVERY_FAILED: "danger",
  INSPECTED: "primary",
  COMPLETED: "success",
  CANCELLED: "neutral",
  DISPUTED: "danger",
};

const STATE_LABEL: Record<OrderState, string> = {
  CREATED: "Created",
  CONFIRMED: "Confirmed",
  FUNDED: "Funded",
  PREPARING: "Preparing",
  IN_TRANSIT: "In transit",
  DELIVERED: "Delivered",
  DELIVERY_FAILED: "Delivery failed",
  INSPECTED: "Inspected",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
  DISPUTED: "Disputed",
};

export function OrderStateBadge({ state }: { state: OrderState }) {
  return <Badge tone={STATE_TONE[state]}>{STATE_LABEL[state]}</Badge>;
}

const SHIPMENT_TONE: Record<ShipmentState, "neutral" | "success" | "warning" | "danger" | "primary"> = {
  CREATED: "neutral",
  ASSIGNED: "primary",
  PICKED_UP: "primary",
  IN_TRANSIT: "warning",
  DELIVERED: "warning",
  CONFIRMED: "success",
  FAILED: "danger",
};

const SHIPMENT_LABEL: Record<ShipmentState, string> = {
  CREATED: "Requested",
  ASSIGNED: "Assigned",
  PICKED_UP: "Picked up",
  IN_TRANSIT: "In transit",
  DELIVERED: "Delivered",
  CONFIRMED: "Confirmed",
  FAILED: "Failed",
};

export function ShipmentStateBadge({ state }: { state: ShipmentState }) {
  return <Badge tone={SHIPMENT_TONE[state]}>{SHIPMENT_LABEL[state]}</Badge>;
}

const LOAN_APPLICATION_TONE: Record<LoanApplicationState, "neutral" | "success" | "warning" | "danger" | "primary"> = {
  APPLICATION: "neutral",
  ASSESSMENT: "warning",
  APPROVED: "primary",
  REJECTED: "danger",
  DISBURSED: "success",
  CANCELLED: "neutral",
};

const LOAN_APPLICATION_LABEL: Record<LoanApplicationState, string> = {
  APPLICATION: "Applied",
  ASSESSMENT: "Under assessment",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  DISBURSED: "Disbursed",
  CANCELLED: "Cancelled",
};

export function LoanApplicationStateBadge({ state }: { state: LoanApplicationState }) {
  return <Badge tone={LOAN_APPLICATION_TONE[state]}>{LOAN_APPLICATION_LABEL[state]}</Badge>;
}

const LOAN_TONE: Record<LoanState, "neutral" | "success" | "warning" | "danger" | "primary"> = {
  DISBURSED: "primary",
  ACTIVE: "primary",
  REPAYING: "warning",
  COMPLETED: "success",
  DEFAULTED: "danger",
};

const LOAN_LABEL: Record<LoanState, string> = {
  DISBURSED: "Disbursed",
  ACTIVE: "Active",
  REPAYING: "Repaying",
  COMPLETED: "Completed",
  DEFAULTED: "Defaulted",
};

export function LoanStateBadge({ state }: { state: LoanState }) {
  return <Badge tone={LOAN_TONE[state]}>{LOAN_LABEL[state]}</Badge>;
}

const POLICY_TONE: Record<InsurancePolicyState, "neutral" | "success" | "warning" | "danger" | "primary"> = {
  PENDING_PAYMENT: "neutral",
  ACTIVE: "primary",
  TRIGGERED: "success",
  EXPIRED: "warning",
  CANCELLED: "danger",
};

const POLICY_LABEL: Record<InsurancePolicyState, string> = {
  PENDING_PAYMENT: "Pending payment",
  ACTIVE: "Active",
  TRIGGERED: "Payout triggered",
  EXPIRED: "Expired",
  CANCELLED: "Cancelled",
};

export function PolicyStateBadge({ state }: { state: InsurancePolicyState }) {
  return <Badge tone={POLICY_TONE[state]}>{POLICY_LABEL[state]}</Badge>;
}

const DISPUTE_TONE: Record<DisputeState, "neutral" | "success" | "warning" | "danger" | "primary"> = {
  OPEN: "danger",
  RESOLVED: "success",
};

const DISPUTE_LABEL: Record<DisputeState, string> = {
  OPEN: "Open",
  RESOLVED: "Resolved",
};

export function DisputeStateBadge({ state }: { state: DisputeState }) {
  return <Badge tone={DISPUTE_TONE[state]}>{DISPUTE_LABEL[state]}</Badge>;
}
