// The backend stores money as integer minor units (kobo, since the platform
// is Nigeria-first) to avoid floating point drift in the ledger. The
// frontend must never do arithmetic on the display string, only format it.

export function formatMinor(amountMinor: number, currency = "NGN"): string {
  const major = amountMinor / 100;
  return new Intl.NumberFormat("en-NG", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(major);
}

export function formatMilli(valueMilli: number, suffix = ""): string {
  const value = valueMilli / 1000;
  return `${value.toLocaleString("en-NG", { maximumFractionDigits: 3 })}${suffix}`;
}
