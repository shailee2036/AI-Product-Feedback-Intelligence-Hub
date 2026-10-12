import { z } from "zod";

export const meSchema = z.object({
  user_id: z.uuid(),
  email: z.string().nullable(),
  workspace: z.object({
    id: z.uuid(),
    name: z.string(),
    role: z.string(),
  }),
});

export const productSchema = z.object({
  id: z.uuid(),
  name: z.string(),
  created_at: z.string(),
  repository: z.object({
    id: z.uuid(),
    github_node_id: z.string(),
    full_name: z.string(),
    html_url: z.url(),
    default_branch: z.string(),
    license_spdx: z.string(),
    license_checked_at: z.string().nullable(),
  }),
});

export const importSchema = z.object({
  id: z.uuid(),
  status: z.enum(["queued", "running", "succeeded", "failed", "cancelled"]),
  issue_limit: z.number(),
  imported_count: z.number(),
  skipped_count: z.number(),
  not_modified: z.boolean(),
  error_message: z.string().nullable(),
  created_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
});

export const feedbackItemSchema = z.object({
  id: z.uuid(),
  source: z.enum(["github_issue", "csv"]),
  number: z.number().nullable(),
  title: z.string(),
  state: z.string().nullable(),
  html_url: z.url().nullable(),
  labels: z.array(z.string()),
  comment_count: z.number(),
  reactions_total: z.number(),
  excerpt: z.string(),
  product_area: z.string().nullable(),
  is_synthetic: z.boolean(),
  updated_at: z.string(),
});

export const feedbackPageSchema = z.object({
  total: z.number(),
  items: z.array(feedbackItemSchema),
});

export const embeddingStatusSchema = z.object({
  id: z.uuid().nullable(),
  status: z.enum(["idle", "queued", "running", "succeeded", "failed", "cancelled"]),
  model: z.string(),
  dimensions: z.number(),
  embedded_count: z.number(),
  skipped_count: z.number(),
  unchanged_count: z.number(),
  redaction_count: z.number(),
  stored_count: z.number(),
  error_message: z.string().nullable(),
});

export const duplicateReportSchema = z.object({
  ran: z.boolean(),
  exact_edges: z.number(),
  semantic_edges: z.number(),
  group_count: z.number(),
  threshold: z.number(),
  neighbor_count: z.number(),
  groups: z.array(
    z.object({
      kind: z.enum(["exact", "semantic", "mixed"]),
      members: z.array(
        z.object({
          id: z.uuid(),
          source: z.enum(["github_issue", "csv"]),
          external_id: z.string(),
          title: z.string(),
        }),
      ),
    }),
  ),
  evaluation: z
    .object({
      labeled: z.number(),
      true_positives: z.number(),
      false_positives: z.number(),
      false_negatives: z.number(),
      precision: z.number().nullable(),
      recall: z.number().nullable(),
    })
    .nullable(),
});

const duplicateWarningSchema = z.object({
  id: z.uuid(),
  number: z.number(),
  title: z.string(),
  html_url: z.string(),
  similarity: z.number(),
  in_theme: z.boolean(),
});

export const clusterReportSchema = z.object({
  ran: z.boolean(),
  cluster_count: z.number(),
  member_count: z.number(),
  threshold: z.number(),
  neighbor_count: z.number(),
  minimum_size: z.number(),
  named_count: z.number(),
  approved_count: z.number(),
  clusters: z.array(
    z.object({
      id: z.uuid(),
      name: z.string().nullable(),
      summary: z.string().nullable(),
      status: z.enum(["open", "approved", "dismissed"]),
      score: z.object({
        member_count: z.number(),
        recent_count: z.number(),
        recent_days: z.number(),
        source_count: z.number(),
        unique_count: z.number(),
        embedded_count: z.number(),
        named: z.boolean(),
        score: z.number(),
      }),
      brief: z
        .object({
          problem: z.string(),
          impact: z.string(),
          evidence_summary: z.string(),
          non_goals: z.string(),
          acceptance_criteria: z.string(),
          open_questions: z.string(),
          evidence_ids: z.array(z.uuid()),
          version: z.number(),
          source: z.enum(["generated", "edited"]),
          history: z.array(
            z.object({
              version: z.number(),
              source: z.enum(["generated", "edited"]),
              problem: z.string(),
              created_at: z.string(),
            }),
          ),
        })
        .nullable(),
      canonical: z
        .object({
          id: z.uuid(),
          number: z.number(),
          title: z.string(),
          html_url: z.string(),
          state: z.enum(["open", "closed"]),
          comment_count: z.number(),
          reactions_total: z.number(),
          coverage: z.number(),
          recent: z.boolean(),
          recent_days: z.number(),
          score: z.number(),
        })
        .nullable(),
      duplicate_warnings: z.array(duplicateWarningSchema),
      suggestion: z
        .object({
          comment: z.string(),
          labels: z.array(z.string()),
          saved: z.boolean(),
        })
        .nullable(),
      new_issue: z
        .object({
          title: z.string(),
          body: z.string(),
          labels: z.array(z.string()),
          warnings: z.array(duplicateWarningSchema),
          saved: z.boolean(),
        })
        .nullable(),
      members: z.array(
        z.object({
          id: z.uuid(),
          source: z.enum(["github_issue", "csv"]),
          external_id: z.string(),
          title: z.string(),
        }),
      ),
    }),
  ),
  evaluation: z
    .object({
      labeled: z.number(),
      gathered: z.number(),
      mean_cohesion: z.number(),
    })
    .nullable(),
});

export const newIssuePreviewSchema = z.object({
  title: z.string(),
  body: z.string(),
  labels: z.array(z.string()),
  warnings: z.array(duplicateWarningSchema),
});

export const auditReportSchema = z.object({
  events: z.array(
    z.object({
      id: z.number(),
      action: z.string(),
      summary: z.string(),
      created_at: z.string(),
    }),
  ),
});

export const csvImportSchema = z.object({
  import_id: z.uuid(),
  imported_count: z.number(),
  warnings: z.array(z.string()),
});

export type Me = z.infer<typeof meSchema>;
export type Product = z.infer<typeof productSchema>;
export type ImportJob = z.infer<typeof importSchema>;
export type FeedbackPage = z.infer<typeof feedbackPageSchema>;
export type FeedbackItem = z.infer<typeof feedbackItemSchema>;
export type CsvImport = z.infer<typeof csvImportSchema>;
export type EmbeddingStatus = z.infer<typeof embeddingStatusSchema>;
export type DuplicateReport = z.infer<typeof duplicateReportSchema>;
export type ClusterReport = z.infer<typeof clusterReportSchema>;
export type NewIssuePreview = z.infer<typeof newIssuePreviewSchema>;
export type AuditReport = z.infer<typeof auditReportSchema>;
