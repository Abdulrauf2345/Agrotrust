import { describe, it, expect } from "vitest";
import { formatDate, formatDateTime, formatRelativeTime } from "./date";

describe("date formatting", () => {
  it("formatDate falls back to a dash for null or undefined", () => {
    expect(formatDate(null)).toBe("-");
    expect(formatDate(undefined)).toBe("-");
  });

  it("formatDate renders a real backend ISO timestamp", () => {
    expect(formatDate("2026-03-15T10:30:00Z")).toMatch(/2026/);
  });

  it("formatDateTime includes a time component", () => {
    const result = formatDateTime("2026-03-15T10:30:00Z");
    expect(result).toMatch(/2026/);
    expect(result.length).toBeGreaterThan(formatDate("2026-03-15T10:30:00Z").length);
  });

  it("formatRelativeTime falls back to a dash for invalid input", () => {
    expect(formatRelativeTime("not-a-date")).toBe("-");
  });
});
