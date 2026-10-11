import { z } from "zod";

const publicSchema = z.object({
  supabaseUrl: z.url(),
  supabasePublishableKey: z.string().min(1),
});

export type PublicEnv = z.infer<typeof publicSchema>;

// NEXT_PUBLIC_* values must be referenced literally so Next.js can inline them at build time.
export function getPublicEnv(): PublicEnv {
  return publicSchema.parse({
    supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL,
    supabasePublishableKey: process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
  });
}
