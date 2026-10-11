import type { Metadata } from "next";

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
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">Feedback Intelligence Hub</h1>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Sign in to turn your open-source project&apos;s issues into product themes.
        </p>
      </div>
      <LoginForm next={safeNextPath(next)} initialError={error ? ERRORS[error] : undefined} />
    </main>
  );
}
