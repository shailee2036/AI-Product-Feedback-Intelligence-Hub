import "server-only";
import type { z } from "zod";

import { getServerEnv } from "@/lib/server-env";

import { ApiError, parseErrorDetail } from "./errors";
import {
  clusterReportSchema,
  csvImportSchema,
  duplicateReportSchema,
  embeddingStatusSchema,
  feedbackPageSchema,
  importSchema,
  meSchema,
  productSchema,
  type ClusterReport,
  type CsvImport,
  type DuplicateReport,
  type EmbeddingStatus,
  type FeedbackPage,
  type ImportJob,
  type Me,
  type Product,
} from "./types";

const TIMEOUT_MS = 15_000;

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH";
  body?: unknown;
  accessToken: string;
};

async function request<S extends z.ZodType>(
  path: string,
  schema: S,
  { method = "GET", body, accessToken }: RequestOptions,
): Promise<z.infer<S>> {
  const { apiUrl } = getServerEnv();
  let response: Response;
  try {
    response = await fetch(new URL(path, apiUrl), {
      method,
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${accessToken}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    throw new ApiError(503, { message: "The API is unreachable.", reasons: [] });
  }

  const payload: unknown = await response.json().catch(() => undefined);
  if (!response.ok) throw new ApiError(response.status, parseErrorDetail(response.status, payload));
  return schema.parse(payload);
}

export function getMe(accessToken: string): Promise<Me> {
  return request("/v1/me", meSchema, { accessToken });
}

export async function getProduct(accessToken: string): Promise<Product | null> {
  try {
    return await request("/v1/product", productSchema, { accessToken });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function startIssueImport(accessToken: string): Promise<ImportJob> {
  return request("/v1/imports", importSchema, { method: "POST", accessToken });
}

export async function getCurrentImport(accessToken: string): Promise<ImportJob | null> {
  try {
    return await request("/v1/imports/current", importSchema, { accessToken });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function cancelIssueImport(accessToken: string, importId: string): Promise<ImportJob> {
  return request(`/v1/imports/${importId}/cancel`, importSchema, { method: "POST", accessToken });
}

export function getFeedback(
  accessToken: string,
  options?: { source?: "github_issue" | "csv"; limit?: number },
): Promise<FeedbackPage> {
  const params = new URLSearchParams({ limit: String(options?.limit ?? 20) });
  if (options?.source) params.set("source", options.source);
  return request(`/v1/feedback?${params}`, feedbackPageSchema, { accessToken });
}

export async function uploadFeedbackCsv(accessToken: string, file: File): Promise<CsvImport> {
  const { apiUrl } = getServerEnv();
  const body = new FormData();
  body.set("file", file);
  let response: Response;
  try {
    response = await fetch(new URL("/v1/product/csv", apiUrl), {
      method: "POST",
      headers: { Accept: "application/json", Authorization: `Bearer ${accessToken}` },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    throw new ApiError(503, { message: "The API is unreachable.", reasons: [] });
  }
  const payload: unknown = await response.json().catch(() => undefined);
  if (!response.ok) throw new ApiError(response.status, parseErrorDetail(response.status, payload));
  return csvImportSchema.parse(payload);
}

export function startEmbeddings(accessToken: string): Promise<EmbeddingStatus> {
  return request("/v1/feedback/embeddings", embeddingStatusSchema, { method: "POST", accessToken });
}

export function getCurrentEmbeddings(accessToken: string): Promise<EmbeddingStatus> {
  return request("/v1/feedback/embeddings/current", embeddingStatusSchema, { accessToken });
}

export function findDuplicates(accessToken: string): Promise<DuplicateReport> {
  return request("/v1/feedback/duplicates", duplicateReportSchema, { method: "POST", accessToken });
}

export function getDuplicates(accessToken: string): Promise<DuplicateReport> {
  return request("/v1/feedback/duplicates", duplicateReportSchema, { accessToken });
}

export function findClusters(accessToken: string): Promise<ClusterReport> {
  return request("/v1/feedback/clusters", clusterReportSchema, { method: "POST", accessToken });
}

export function getClusters(accessToken: string): Promise<ClusterReport> {
  return request("/v1/feedback/clusters", clusterReportSchema, { accessToken });
}

export function nameClusters(accessToken: string): Promise<ClusterReport> {
  return request("/v1/feedback/clusters/names", clusterReportSchema, {
    method: "POST",
    accessToken,
  });
}

export function relabelCluster(
  accessToken: string,
  clusterId: string,
  name: string,
  summary: string,
): Promise<ClusterReport> {
  return request(`/v1/feedback/clusters/${clusterId}`, clusterReportSchema, {
    method: "PATCH",
    body: { name, summary },
    accessToken,
  });
}

export function decideCluster(
  accessToken: string,
  clusterId: string,
  decision: "approve" | "dismiss",
): Promise<ClusterReport> {
  return request(`/v1/feedback/clusters/${clusterId}/decision`, clusterReportSchema, {
    method: "POST",
    body: { decision },
    accessToken,
  });
}

export function mergeClusters(
  accessToken: string,
  clusterId: string,
  targetId: string,
): Promise<ClusterReport> {
  return request(`/v1/feedback/clusters/${clusterId}/merge`, clusterReportSchema, {
    method: "POST",
    body: { target_id: targetId },
    accessToken,
  });
}

export function splitCluster(
  accessToken: string,
  clusterId: string,
  memberIds: string[],
): Promise<ClusterReport> {
  return request(`/v1/feedback/clusters/${clusterId}/split`, clusterReportSchema, {
    method: "POST",
    body: { member_ids: memberIds },
    accessToken,
  });
}

export function saveClusterSuggestion(
  accessToken: string,
  clusterId: string,
): Promise<ClusterReport> {
  return request(`/v1/feedback/clusters/${clusterId}/suggestion`, clusterReportSchema, {
    method: "POST",
    accessToken,
  });
}

export function writeClusterBrief(accessToken: string, clusterId: string): Promise<ClusterReport> {
  return request(`/v1/feedback/clusters/${clusterId}/brief`, clusterReportSchema, {
    method: "POST",
    accessToken,
  });
}

export function editClusterBrief(
  accessToken: string,
  clusterId: string,
  brief: {
    problem: string;
    impact: string;
    evidence_summary: string;
    non_goals: string;
    acceptance_criteria: string;
    open_questions: string;
  },
): Promise<ClusterReport> {
  return request(`/v1/feedback/clusters/${clusterId}/brief`, clusterReportSchema, {
    method: "PATCH",
    body: brief,
    accessToken,
  });
}

export function registerGithubProduct(accessToken: string, repository: string): Promise<Product> {
  return request("/v1/product/github", productSchema, {
    method: "POST",
    body: { repository },
    accessToken,
  });
}
