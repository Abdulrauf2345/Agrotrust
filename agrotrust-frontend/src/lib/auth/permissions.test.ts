import { describe, it, expect } from "vitest";
import { roleHasPermission, primaryRole } from "./permissions";

describe("roleHasPermission", () => {
  it("grants a buyer order:create", () => {
    expect(roleHasPermission(["BUYER"], "order:create")).toBe(true);
  });

  it("does not grant a buyer listing:create", () => {
    expect(roleHasPermission(["BUYER"], "listing:create")).toBe(false);
  });

  it("grants a farmer listing:create", () => {
    expect(roleHasPermission(["FARMER"], "listing:create")).toBe(true);
  });

  it("grants PLATFORM_ADMIN admin:users", () => {
    expect(roleHasPermission(["PLATFORM_ADMIN"], "admin:users")).toBe(true);
  });

  it("checks across multiple roles on one user", () => {
    expect(roleHasPermission(["BUYER", "FARMER"], "listing:create")).toBe(true);
  });
});

describe("primaryRole", () => {
  it("returns the first role", () => {
    expect(primaryRole(["FARMER", "BUYER"])).toBe("FARMER");
  });

  it("returns null for an empty role list", () => {
    expect(primaryRole([])).toBeNull();
  });
});
