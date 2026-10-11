import { describe, expect, it } from "vitest";

import { credentialsSchema } from "./auth-schema";

describe("credentialsSchema", () => {
  it("accepts a valid email and password", () => {
    expect(credentialsSchema.safeParse({ email: "pm@example.com", password: "longenough" }).success).toBe(
      true,
    );
  });

  it.each([
    [{ email: "not-an-email", password: "longenough" }, "Enter a valid email address."],
    [{ email: "pm@example.com", password: "short" }, "Password must be at least 8 characters."],
    [{ email: "pm@example.com", password: "x".repeat(73) }, "Password must be at most 72 characters."],
  ])("rejects %o", (input, message) => {
    const result = credentialsSchema.safeParse(input);
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.message).toBe(message);
  });

  it("rejects missing fields from FormData", () => {
    expect(credentialsSchema.safeParse({ email: null, password: null }).success).toBe(false);
  });
});
