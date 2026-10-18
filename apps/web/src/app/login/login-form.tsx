"use client";

import { useActionState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { AuthFormState } from "@/lib/auth-schema";

import { authenticate } from "./actions";

export function LoginForm({ next, initialError }: { next: string; initialError?: string }) {
  const [state, formAction, pending] = useActionState<AuthFormState, FormData>(authenticate, {
    error: initialError,
  });

  return (
    <form action={formAction} className="flex flex-col gap-4">
      <input type="hidden" name="next" value={next} />
      <label className="flex flex-col gap-1 text-sm font-medium">
        Email
        <Input name="email" type="email" autoComplete="email" required />
      </label>
      <label className="flex flex-col gap-1 text-sm font-medium">
        Password
        <Input name="password" type="password" autoComplete="current-password" minLength={8} required />
      </label>

      {state.error ? (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
          {state.error}
        </p>
      ) : null}
      {state.message ? (
        <p
          role="status"
          className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
        >
          {state.message}
        </p>
      ) : null}

      <div className="flex gap-3">
        <Button type="submit" name="intent" value="signin" disabled={pending} className="flex-1">
          Sign in
        </Button>
        <Button
          type="submit"
          name="intent"
          value="signup"
          disabled={pending}
          variant="secondary"
          className="flex-1"
        >
          Create account
        </Button>
      </div>
    </form>
  );
}
