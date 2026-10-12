import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  cancelIssueImport,
  findDuplicates,
  getCurrentEmbeddings,
  getCurrentImport,
  getDuplicates,
  getFeedback,
  getMe,
  getProduct,
  registerGithubProduct,
  startEmbeddings,
  startIssueImport,
  uploadFeedbackCsv,
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
            source: "github_issue",
            number: 42,
            title: "Login fails",
            state: "open",
            html_url: "https://github.com/appwrite/appwrite/issues/42",
            labels: ["bug"],
            comment_count: 1,
            reactions_total: 2,
            excerpt: "Customers cannot complete login.",
            product_area: null,
            is_synthetic: false,
            updated_at: "2026-10-11T00:00:00Z",
          },
        ],
      }),
    );
    const page = await getFeedback("t", { source: "github_issue", limit: 20 });
    expect(page.total).toBe(1);
    expect(page.items[0]?.title).toBe("Login fails");
    expect(String(fetchMock.mock.calls[1][0])).toContain("source=github_issue");
  });

  it("uploads a csv without setting a content type", async () => {
    fetchMock.mockResolvedValue(
      respond(201, {
        import_id: "5f0c7a52-79a1-4a8a-9d43-5d1f9c1a2b3c",
        imported_count: 42,
        warnings: [],
      }),
    );

    const saved = await uploadFeedbackCsv("t", new File(["id,feedback"], "feedback.csv", { type: "text/csv" }));

    expect(saved.imported_count).toBe(42);
    const init = fetchMock.mock.calls[0][1];
    expect(init?.body).toBeInstanceOf(FormData);
    expect(new Headers(init?.headers).get("Content-Type")).toBeNull();
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://api.test/v1/product/csv");
  });

  it("starts an embedding run and reads its status", async () => {
    const status = {
      id: "5f0c7a52-79a1-4a8a-9d43-5d1f9c1a2b3c",
      status: "queued",
      model: "gemini-embedding-001",
      dimensions: 768,
      embedded_count: 0,
      skipped_count: 0,
      unchanged_count: 0,
      redaction_count: 0,
      stored_count: 12,
      error_message: null,
    };
    fetchMock.mockResolvedValueOnce(respond(202, status));
    fetchMock.mockResolvedValueOnce(respond(200, { ...status, status: "succeeded", embedded_count: 12 }));

    const started = await startEmbeddings("t");
    const current = await getCurrentEmbeddings("t");

    expect(started.status).toBe("queued");
    expect(current.embedded_count).toBe(12);
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://api.test/v1/feedback/embeddings");
    expect(String(fetchMock.mock.calls[1][0])).toBe("http://api.test/v1/feedback/embeddings/current");
  });

  it("finds duplicates and reads the stored groups", async () => {
    const report = {
      ran: true,
      exact_edges: 1,
      semantic_edges: 2,
      group_count: 3,
      threshold: 0.86,
      neighbor_count: 2,
      groups: [
        {
          kind: "exact",
          members: [
            {
              id: "5f0c7a52-79a1-4a8a-9d43-5d1f9c1a2b3c",
              source: "csv",
              external_id: "AW-SYN-001",
              title: "Callback checklist",
            },
            {
              id: "6f0c7a52-79a1-4a8a-9d43-5d1f9c1a2b3c",
              source: "csv",
              external_id: "AW-SYN-002",
              title: "Callback rejected",
            },
          ],
        },
      ],
      evaluation: {
        labeled: 3,
        true_positives: 1,
        false_positives: 0,
        false_negatives: 1,
        precision: 1,
        recall: 0.5,
      },
    };
    fetchMock.mockResolvedValueOnce(respond(200, report));
    fetchMock.mockResolvedValueOnce(respond(200, { ...report, ran: true }));

    const found = await findDuplicates("t");
    const current = await getDuplicates("t");

    expect(found.group_count).toBe(3);
    expect(current.evaluation?.recall).toBe(0.5);
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://api.test/v1/feedback/duplicates");
    expect(fetchMock.mock.calls[0][1]?.method).toBe("POST");
    expect(fetchMock.mock.calls[1][1]?.method).toBe("GET");
  });

  it("rejects responses that do not match the contract", async () => {
    fetchMock.mockResolvedValue(respond(200, { user_id: "not-a-uuid" }));

    await expect(getMe("t")).rejects.toThrow();
  });
});
