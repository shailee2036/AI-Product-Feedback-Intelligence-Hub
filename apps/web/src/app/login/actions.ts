"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { credentialsSchema, type AuthFormState } from "@/lib/auth-schema";
import { safeNextPath } from "@/lib/redirects";
import { createSupabaseServerClient } from "@/lib/supabase/server";

async function siteOrigin(): Promise<string> {
  if (process.env.SITE_URL) return process.env.SITE_URL.replace(/\/$/, "");
  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "localhost:3100";
  const proto = h.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  return `${proto}://${host}`;
}

export async function authenticate(
  _previous: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  const parsed = credentialsSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
  });
  if (!parsed.success) {
    return { error: parsed.error.issues[0]?.message ?? "Invalid input." };
  }

  const supabase = await createSupabaseServerClient();
  const next = safeNextPath(formData.get("next")?.toString());

  if (formData.get("intent") === "signup") {
    const callback = new URL("/auth/callback", await siteOrigin());
    callback.searchParams.set("next", next);
    const { data, error } = await supabase.auth.signUp({
      ...parsed.data,
      options: { emailRedirectTo: callback.toString() },
    });
    if (error) return { error: error.message };
    if (data.session) redirect(next);
    return { message: "Check your inbox and click the confirmation link to finish signing up." };
  }

  const { error } = await supabase.auth.signInWithPassword(parsed.data);
  if (error) {
    return error.code === "email_not_confirmed"
      ? { error: "Confirm your email address first, then sign in." }
      : { error: "Incorrect email or password." };
  }
  redirect(next);
}

export async function signOut(): Promise<void> {
  const supabase = await createSupabaseServerClient();
  await supabase.auth.signOut();
  redirect("/login");
}
