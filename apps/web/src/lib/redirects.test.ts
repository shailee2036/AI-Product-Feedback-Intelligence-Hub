import { describe, expect, it } from "vitest";

import { safeNextPath } from "./redirects";

describe("safeNextPath", () => {
  it.each([
    ["/dashboard", "/dashboard"],
    ["/dashboard?tab=themes", "/dashboard?tab=themes"],
    ["/dashboard/settings", "/dashboard/settings"],
  ])("keeps same-site path %s", (input, expected) => {
    expect(safeNextPath(input)).toBe(expected);
  });

  it.each([
    null,
    undefined,
    "",
    "dashboard",
    "https://evil.example/phish",
    "//evil.example",
    "/\\evil.example",
    "javascript:alert(1)",
  ])("falls back to the dashboard for %s", (input) => {
    expect(safeNextPath(input)).toBe("/dashboard");
  });
});
