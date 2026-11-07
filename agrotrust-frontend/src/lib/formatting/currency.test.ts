import { describe, it, expect } from "vitest";
import { formatMinor } from "./currency";

describe("formatMinor", () => {
  it("converts minor units to a formatted major-unit currency string", () => {
    expect(formatMinor(150000)).toContain("1,500");
  });

  it("handles zero", () => {
    expect(formatMinor(0)).toContain("0");
  });

  it("handles amounts under one major unit", () => {
    expect(formatMinor(50)).toContain("0.5");
  });

  it("respects a non-default currency code", () => {
    const result = formatMinor(100000, "USD");
    expect(result).toMatch(/\$|USD/);
  });
});
