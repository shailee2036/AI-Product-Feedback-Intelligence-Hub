"use client";

import { useActionState } from "react";

import { registerRepository, type RegisterState } from "./actions";

export function RegisterRepositoryForm() {
  const [state, formAction, pending] = useActionState<RegisterState, FormData>(
    registerRepository,
    {},
  );

  return (
    <form action={formAction} className="flex flex-col gap-3">
      <label htmlFor="repository" className="text-sm font-medium">
        GitHub repository
      </label>
      <div className="flex gap-3">
        <input
          id="repository"
          name="repository"
          defaultValue={state.repository ?? ""}
          placeholder="appwrite/appwrite or https://github.com/appwrite/appwrite"
          required
          className="flex-1 rounded-md border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-zinc-700 dark:bg-zinc-900"
        />
        <button
          type="submit"
          disabled={pending}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-60"
        >
          {pending ? "Checking…" : "Register"}
        </button>
      </div>
      <p className="text-xs text-zinc-500">
        Must be public, owned by a GitHub organization, open-source licensed, with Issues enabled.
      </p>

      {state.error ? (
        <div role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
          <p>{state.error}</p>
          {state.reasons?.length ? (
            <ul className="mt-1 list-disc pl-5">
              {state.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </form>
  );
}
