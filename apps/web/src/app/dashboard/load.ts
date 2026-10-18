import { redirect } from "next/navigation";

import {
  getAudit,
  getClusters,
  getCurrentEmbeddings,
  getCurrentImport,
  getDuplicates,
  getFeedback,
  getMe,
  getProduct,
} from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type {
  AuditReport,
  ClusterReport,
  DuplicateReport,
  EmbeddingStatus,
  FeedbackPage,
  ImportJob,
  Me,
  Product,
} from "@/lib/api/types";
import { getVerifiedAccessToken } from "@/lib/supabase/server";

export const EMPTY_FEEDBACK: FeedbackPage = { total: 0, items: [] };

export type Workspace =
  | {
      me: Me;
      product: Product | null;
      audit: AuditReport;
      job: ImportJob | null;
      feedback: FeedbackPage;
      csvFeedback: FeedbackPage;
      embeddings: EmbeddingStatus | null;
      duplicates: DuplicateReport | null;
      clusters: ClusterReport | null;
    }
  | { error: string };

export async function requireToken(next = "/dashboard"): Promise<string> {
  const token = await getVerifiedAccessToken();
  if (!token) redirect(`/login?next=${encodeURIComponent(next)}`);
  return token;
}

export async function loadWorkspace(): Promise<Workspace> {
  const token = await requireToken();
  try {
    const me = await getMe(token);
    const [product, audit] = await Promise.all([getProduct(token), getAudit(token)]);
    if (!product) {
      return {
        me,
        product,
        audit,
        job: null,
        feedback: EMPTY_FEEDBACK,
        csvFeedback: EMPTY_FEEDBACK,
        embeddings: null,
        duplicates: null,
        clusters: null,
      };
    }
    const [job, feedback, csvFeedback, embeddings, duplicates, clusters] = await Promise.all([
      getCurrentImport(token),
      getFeedback(token, { source: "github_issue", limit: 20 }),
      getFeedback(token, { source: "csv", limit: 50 }),
      getCurrentEmbeddings(token),
      getDuplicates(token),
      getClusters(token),
    ]);
    return { me, product, audit, job, feedback, csvFeedback, embeddings, duplicates, clusters };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?next=/dashboard");
    return { error: error instanceof ApiError ? error.detail.message : "Something went wrong." };
  }
}
