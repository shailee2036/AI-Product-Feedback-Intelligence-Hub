import type { Metadata } from "next";
import Link from "next/link";

import { safeNextPath } from "@/lib/redirects";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in · Feedback Intelligence Hub" };

const ERRORS: Record<string, string> = {
  confirmation_failed: "That confirmation link is invalid or has expired. Sign in or request a new one.",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; error?: string }>;
}) {
  const { next, error } = await searchParams;

  return (
    <main className="grid min-h-screen lg:grid-cols-2">
      <section className="hidden flex-col justify-between bg-sidebar px-12 py-12 text-sidebar-foreground lg:flex">
        <Link href="/" className="text-sm font-semibold tracking-tight text-teal-100">
          Feedback Intelligence Hub
        </Link>
        <div className="max-w-md">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-coral">Workspace</p>
          <p className="mt-3 text-3xl font-semibold tracking-tight text-balance">
            One public repository. Themes with evidence. No silent GitHub writes.
          </p>
          <p className="mt-4 text-sm text-teal-100/75">
            Sign in to import issues, group feedback, and approve briefs that cite only the rows in
            that theme.
          </p>
        </div>
        <p className="text-xs text-teal-200/60">Staging workspace · one product per account</p>
      </section>
      <section className="flex flex-col justify-center px-6 py-16">
        <div className="mx-auto w-full max-w-sm rounded-3xl border border-border bg-card/90 p-8 shadow-[0_18px_40px_-24px_rgba(15,61,54,0.5)]">
          <Link href="/" className="mb-6 inline-block text-sm font-medium text-accent lg:hidden">
            Feedback Intelligence Hub
          </Link>
          <h1 className="text-2xl font-semibold tracking-tight">Welcome back</h1>
          <p className="mt-1 text-sm text-muted">
            Sign in to your workspace, or create an account with the same form.
          </p>
          <div className="mt-8">
            <LoginForm next={safeNextPath(next)} initialError={error ? ERRORS[error] : undefined} />
          </div>
        </div>
      </section>
    </main>
  );
}
