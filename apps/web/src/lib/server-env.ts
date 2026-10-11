import "server-only";
import { z } from "zod";

const serverSchema = z.object({
  apiUrl: z.url(),
  siteUrl: z.url().optional(),
});

export type ServerEnv = z.infer<typeof serverSchema>;

export function getServerEnv(): ServerEnv {
  return serverSchema.parse({
    apiUrl: process.env.API_URL,
    siteUrl: process.env.SITE_URL || undefined,
  });
}
