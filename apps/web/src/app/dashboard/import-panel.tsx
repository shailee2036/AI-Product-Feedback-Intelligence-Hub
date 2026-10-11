"use client";

import { useActionState, useEffect } from "react";
import { useRouter } from "next/navigation";

import type { FeedbackPage, ImportJob } from "@/lib/api/types";

import { cancelImport, startImport, type ImportState } from "./actions";

export function ImportPanel({
  job,
  feedback,
}: {
  job: ImportJob | null;
  feedback: FeedbackPage;
}) {
  const active = job?.status === "queued" || job?.status === "running";

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-zinc-200 p-6 dark:border-zinc-800">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">GitHub issues</h2>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            {describeJob(job, feedback.total)}
          </p>
        </div>
        {active && job ? <CancelButton importId={job.id} /> : <StartButton />}
      </div>
      {active ? <ImportRefresh /> : null}
      {feedback.items.length ? (
        <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
          {feedback.items.map((item) => (
            <li key={item.id} className="py-3">
              <div className="flex items-baseline justify-between gap-3">
                <a
                  href={item.html_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-indigo-600 hover:underline"
                >
                  #{item.number} {item.title}
                </a>
                <span className="shrink-0 text-xs uppercase tracking-wide text-zinc-500">{item.state}</span>
              </div>
              {item.excerpt ? (
                <p className="mt-1 line-clamp-2 text-sm text-zinc-600 dark:text-zinc-400">{item.excerpt}</p>
              ) : null}
              {item.labels.length ? (
                <ul className="mt-2 flex flex-wrap gap-1">
                  {item.labels.map((label) => (
                    <li key={label} className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                      {label}
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function StartButton() {
  const [state, formAction, pending] = useActionState<ImportState, FormData>(startImport, {});
  return (
    <form action={formAction} className="flex flex-col items-end gap-2">
      <button
        type="submit"
        disabled={pending}
        className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-60"
      >
        {pending ? "Starting…" : "Import issues"}
      </button>
      {state.error ? (
        <p role="alert" className="max-w-xs text-right text-sm text-red-700 dark:text-red-300">
          {state.error}
        </p>
      ) : null}
    </form>
  );
}

function CancelButton({ importId }: { importId: string }) {
  const [state, formAction, pending] = useActionState<ImportState, FormData>(cancelImport, {});
  return (
    <form action={formAction}>
      <input type="hidden" name="importId" value={importId} />
      <button
        type="submit"
        disabled={pending}
        className="rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium hover:bg-zinc-50 disabled:opacity-60 dark:border-zinc-700 dark:hover:bg-zinc-900"
      >
        {pending ? "Cancelling…" : "Cancel"}
      </button>
      {state.error ? (
        <p role="alert" className="mt-2 text-sm text-red-700 dark:text-red-300">
          {state.error}
        </p>
      ) : null}
    </form>
  );
}

function ImportRefresh() {
  const router = useRouter();
  useEffect(() => {
    const timer = setInterval(() => router.refresh(), 2000);
    return () => clearInterval(timer);
  }, [router]);
  return null;
}

function describeJob(job: ImportJob | null, total: number): string {
  if (!job) {
    return "Import the most recently updated public issues. Pull requests are skipped.";
  }
  if (job.status === "queued" || job.status === "running") {
    return `Importing up to ${job.issue_limit} issues… ${job.imported_count} saved so far.`;
  }
  if (job.status === "failed") {
    return job.error_message ?? "The import failed.";
  }
  if (job.status === "cancelled") {
    return `Import cancelled. ${total} issues are saved.`;
  }
  if (job.not_modified) {
    return `No issues changed since the last import. ${total} issues are saved.`;
  }
  return `Imported ${job.imported_count} issues (${job.skipped_count} skipped). ${total} saved in total.`;
}
