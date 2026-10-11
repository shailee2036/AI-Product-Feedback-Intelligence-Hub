import { describe, expect, it } from "vitest";

import { parseRepositoryInput } from "./repository";

describe("parseRepositoryInput", () => {
  it.each([
    "appwrite/appwrite",
    "  appwrite/appwrite  ",
    "https://github.com/appwrite/appwrite",
    "https://github.com/appwrite/appwrite/",
    "https://github.com/appwrite/appwrite.git",
    "https://www.github.com/appwrite/appwrite",
  ])("normalizes %s", (input) => {
    expect(parseRepositoryInput(input)).toEqual({ ok: true, value: "appwrite/appwrite" });
  });

  it.each([
    [null, "Enter a repository"],
    ["", "Enter a repository"],
    ["appwrite", "owner/repo"],
    ["appwrite/appwrite/issues", "owner/repo"],
    ["https://gitlab.com/appwrite/appwrite", "Only github.com"],
    ["https://github.com.evil.example/a/b", "Only github.com"],
    ["https://github.com/appwrite/appwrite?tab=readme", "query strings"],
    ["https://", "not valid"],
    ["-owner/repo", "owner name"],
    ["owner-/repo", "owner name"],
    ["own--er/repo", "owner name"],
    ["owner/re po", "repository name"],
    ["owner/..", "repository name"],
  ])("rejects %s", (input, message) => {
    const result = parseRepositoryInput(input);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain(message);
  });
});
