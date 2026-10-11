import { afterEach, describe, expect, it, vi } from "vitest";

import { getPublicEnv } from "./env";
import { getServerEnv } from "./server-env";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("getPublicEnv", () => {
  it("reads the Supabase URL and publishable key", () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://abc.supabase.co");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test");

    expect(getPublicEnv()).toEqual({
      supabaseUrl: "https://abc.supabase.co",
      supabasePublishableKey: "sb_publishable_test",
    });
  });

  it("fails fast when configuration is missing", () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "");

    expect(() => getPublicEnv()).toThrow();
  });
});

describe("getServerEnv", () => {
  it("reads the API URL and treats an empty SITE_URL as unset", () => {
    vi.stubEnv("API_URL", "http://127.0.0.1:8000");
    vi.stubEnv("SITE_URL", "");

    expect(getServerEnv()).toEqual({ apiUrl: "http://127.0.0.1:8000", siteUrl: undefined });
  });

  it("rejects an invalid API URL", () => {
    vi.stubEnv("API_URL", "not a url");

    expect(() => getServerEnv()).toThrow();
  });
});
