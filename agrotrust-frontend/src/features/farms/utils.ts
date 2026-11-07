import type { FarmVerificationStatus } from "@/types/api";

const TONE_BY_STATUS: Record<FarmVerificationStatus, "neutral" | "warning" | "success" | "danger" | "primary"> = {
  UNVERIFIED: "neutral",
  PENDING: "warning",
  ASSIGNED: "warning",
  VISITED: "primary",
  SUBMITTED: "primary",
  UNDER_REVIEW: "primary",
  VERIFIED: "success",
  REJECTED: "danger",
};

export function verificationTone(status: FarmVerificationStatus) {
  return TONE_BY_STATUS[status];
}

export function verificationLabel(status: FarmVerificationStatus): string {
  return status
    .toLowerCase()
    .split("_")
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}
