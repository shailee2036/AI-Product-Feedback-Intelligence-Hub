"use client";

import { useActionState, useEffect } from "react";
import { useRouter } from "next/navigation";

import type { EmbeddingStatus } from "@/lib/api/types";

import { startEmbedding, type EmbeddingState } from "./actions";

export function EmbeddingPanel({ status }: { status: EmbeddingStatus }) {
  const active = status.status === "queued" || status.status === "running";

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-zinc-200 p-6 dark:border-zinc-800">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Embeddings</h2>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{describe(status)}</p>
          <p className="mt-1 text-xs text-zinc-500">
            {status.model} · {status.dimensions} dimensions · {status.stored_count} stored
          </p>
        </div>
        {active ? null : <EmbedButton />}
      </div>
      {active ? <EmbeddingRefresh /> : null}
    </section>
  );
}

function EmbedButton() {
  const [state, formAction, pending] = useActionState<EmbeddingState, FormData>(startEmbedding, {});
  return (
    <form action={formAction} className="flex flex-col items-end gap-2">
      <button
        type="submit"
        disabled={pending}
        className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-60"
      >
        {pending ? "Starting…" : "Embed feedback"}
      </button>
      {state.error ? (
        <p role="alert" className="max-w-xs text-right text-sm text-red-700 dark:text-red-300">
          {state.error}
        </p>
      ) : null}
    </form>
  );
}

function EmbeddingRefresh() {
  const router = useRouter();
  useEffect(() => {
    const timer = setInterval(() => router.refresh(), 2000);
    return () => clearInterval(timer);
  }, [router]);
  return null;
}

function describe(status: EmbeddingStatus): string {
  if (status.status === "queued" || status.status === "running") {
    return "Embedding saved feedback. Contact details are removed before the text is sent.";
  }
  if (status.status === "failed") {
    return status.error_message ?? "Embedding failed.";
  }
  if (status.status === "succeeded" || status.stored_count > 0) {
    return `Embedded ${status.embedded_count}. Skipped ${status.skipped_count}. ${status.unchanged_count} were already current.`;
  }
  return "Embed saved feedback. Emails, phone numbers, and tokens are removed before anything is sent.";
}
