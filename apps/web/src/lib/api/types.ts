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

export type Me = z.infer<typeof meSchema>;
export type Product = z.infer<typeof productSchema>;
