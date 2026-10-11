import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  cancelIssueImport,
  getCurrentImport,
  getFeedback,
  getMe,
  getProduct,
  registerGithubProduct,
  startIssueImport,
} from "./client";
import { ApiError } from "./errors";

const PRODUCT = {
  id: "5f0c7a52-79a1-4a8a-9d43-5d1f9c1a2b3c",
  name: "appwrite",
  created_at: "2026-10-11T20:00:00Z",
  repository: {
    id: "8a4b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d",
    github_node_id: "MDEwOlJlcG9zaXRvcnkxNjE3NDQ1MjA=",
    full_name: "appwrite/appwrite",
    html_url: "https://github.com/appwrite/appwrite",
    default_branch: "main",
    license_spdx: "BSD-3-Clause",
    license_checked_at: "2026-10-11T20:00:00Z",
  },
};

const fetchMock = vi.fn<typeof fetch>();

function respond(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  vi.stubEnv("API_URL", "http://api.test");
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

describe("API client", () => {
  it("sends the bearer token and validates the response", async () => {
    fetchMock.mockResolvedValue(
      respond(200, {
        user_id: "0b6f6d4e-1d6a-4c2b-9f2a-3c4d5e6f7a8b",
        email: "pm@example.com",
        workspace: { id: "1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f", name: "pm's workspace", role: "owner" },
      }),
    );

    const me = await getMe("token-123");

    expect(me.workspace.role).toBe("owner");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://api.test/v1/me");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer token-123");
    expect(init?.cache).toBe("no-store");
  });

  it("returns null when no product is registered", async () => {
    fetchMock.mockResolvedValue(respond(404, { detail: "No product registered yet." }));

    await expect(getProduct("t")).resolves.toBeNull();
  });

  it("posts the repository and parses the created product", async () => {
    fetchMock.mockResolvedValue(respond(201, PRODUCT));

    const product = await registerGithubProduct("t", "appwrite/appwrite");

    expect(product.repository.license_spdx).toBe("BSD-3-Clause");
    const init = fetchMock.mock.calls[0][1];
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ repository: "appwrite/appwrite" }));
  });

  it("surfaces eligibility reasons as an ApiError", async () => {
    fetchMock.mockResolvedValue(
      respond(422, { detail: { message: "Repository is not eligible.", reasons: ["archived"] } }),
    );

    const error = await registerGithubProduct("t", "appwrite/appwrite").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(422);
    expect((error as ApiError).detail.reasons).toEqual(["archived"]);
  });

  it("rethrows non-404 errors from getProduct", async () => {
    fetchMock.mockResolvedValue(respond(500));

    await expect(getProduct("t")).rejects.toMatchObject({ status: 500 });
  });

  it("maps network failures to a 503 ApiError", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));

    await expect(getMe("t")).rejects.toMatchObject({ status: 503 });
  });

  it("starts an import and reads it back", async () => {
    const job = {
      id: "5f0c7a52-79a1-4a8a-9d43-5d1f9c1a2b3c",
      status: "queued",
      issue_limit: 100,
      imported_count: 0,
      skipped_count: 0,
      not_modified: false,
      error_message: null,
      created_at: "2026-10-11T20:00:00Z",
      started_at: null,
      finished_at: null,
    };
    fetchMock.mockResolvedValue(respond(202, job));

    await expect(startIssueImport("t")).resolves.toMatchObject({ status: "queued" });
    expect(fetchMock.mock.calls[0][1]?.method).toBe("POST");

    fetchMock.mockResolvedValue(respond(404, { detail: "No import has been started." }));
    await expect(getCurrentImport("t")).resolves.toBeNull();
  });

  it("cancels an import and lists imported issues", async () => {
    fetchMock.mockResolvedValueOnce(
      respond(200, {
        id: "5f0c7a52-79a1-4a8a-9d43-5d1f9c1a2b3c",
        status: "cancelled",
        issue_limit: 100,
        imported_count: 0,
        skipped_count: 0,
        not_modified: false,
        error_message: null,
        created_at: "2026-10-11T20:00:00Z",
        started_at: "2026-10-11T20:00:01Z",
        finished_at: "2026-10-11T20:00:02Z",
      }),
    );
    const cancelled = await cancelIssueImport("t", "5f0c7a52-79a1-4a8a-9d43-5d1f9c1a2b3c");
    expect(cancelled.status).toBe("cancelled");
    expect(String(fetchMock.mock.calls[0][0])).toContain("/v1/imports/5f0c7a52-79a1-4a8a-9d43-5d1f9c1a2b3c/cancel");

    fetchMock.mockResolvedValueOnce(
      respond(200, {
        total: 1,
        items: [
          {
            id: "8a4b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d",
            number: 42,
            title: "Login fails",
            state: "open",
            html_url: "https://github.com/appwrite/appwrite/issues/42",
            labels: ["bug"],
            comment_count: 1,
            reactions_total: 2,
            excerpt: "Customers cannot complete login.",
            updated_at: "2026-10-11T00:00:00Z",
          },
        ],
      }),
    );
    const page = await getFeedback("t");
    expect(page.total).toBe(1);
    expect(page.items[0]?.title).toBe("Login fails");
  });

  it("rejects responses that do not match the contract", async () => {
    fetchMock.mockResolvedValue(respond(200, { user_id: "not-a-uuid" }));

    await expect(getMe("t")).rejects.toThrow();
  });
});
