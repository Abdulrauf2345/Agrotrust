import { describe, it, expect } from "vitest";
import { verificationTone, verificationLabel } from "./utils";

describe("farm verification helpers", () => {
  it("maps VERIFIED to a success tone", () => {
    expect(verificationTone("VERIFIED")).toBe("success");
  });

  it("maps REJECTED to a danger tone", () => {
    expect(verificationTone("REJECTED")).toBe("danger");
  });

  it("formats a multi-word status into title case", () => {
    expect(verificationLabel("UNDER_REVIEW")).toBe("Under Review");
  });
});
