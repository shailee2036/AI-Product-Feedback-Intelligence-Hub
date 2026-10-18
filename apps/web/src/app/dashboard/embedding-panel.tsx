"use client";

import { useActionState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import type { EmbeddingStatus } from "@/lib/api/types";

import { startEmbedding, type EmbeddingState } from "./actions";

export function EmbeddingPanel({ status }: { status: EmbeddingStatus }) {
  const active = status.status === "queued" || status.status === "running";

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <CardTitle>Embeddings</CardTitle>
          <CardDescription>{describe(status)}</CardDescription>
          <p className="mt-1 text-xs text-zinc-500">
            {status.model} · {status.dimensions} dimensions · {status.stored_count} stored
          </p>
        </div>
        {active ? null : <EmbedButton />}
      </div>
      {status.status === "failed" && status.error_message ? (
        <p
          role="alert"
          className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300"
        >
          {explainFailure(status.error_message)}
        </p>
      ) : null}
      {active ? <EmbeddingRefresh /> : null}
    </Card>
  );
}

function EmbedButton() {
  const router = useRouter();
  const [state, formAction, pending] = useActionState<EmbeddingState, FormData>(startEmbedding, {});
  const wasPending = useRef(false);
  useEffect(() => {
    if (wasPending.current && !pending) router.refresh();
    wasPending.current = pending;
  }, [pending, router]);
  return (
    <form action={formAction} className="flex flex-col items-end gap-2">
      <Button type="submit" disabled={pending}>
        {pending ? "Starting…" : "Embed feedback"}
      </Button>
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

function explainFailure(message: string): string {
  if (message.includes("402")) {
    return "Hugging Face has no credits left for embeddings. Add credits, then try again.";
  }
  return message;
}

function describe(status: EmbeddingStatus): string {
  if (status.status === "queued" || status.status === "running") {
    return "Embedding saved feedback. Contact details are removed before the text is sent.";
  }
  if (status.status === "failed") {
    return "The last embedding run did not finish.";
  }
  if (status.status === "succeeded" || status.stored_count > 0) {
    return `Embedded ${status.embedded_count}. Skipped ${status.skipped_count}. ${status.unchanged_count} were already current.`;
  }
  return "Embed saved feedback. Emails, phone numbers, and tokens are removed before anything is sent.";
}
