"use client";

import { useActionState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import type { FeedbackPage } from "@/lib/api/types";

import { uploadCsv, type CsvUploadState } from "./actions";

export function CsvPanel({ feedback }: { feedback: FeedbackPage }) {
  const [state, formAction, pending] = useActionState<CsvUploadState, FormData>(uploadCsv, {});

  return (
    <Card className="flex flex-col gap-4">
      <div>
        <CardTitle>Customer feedback</CardTitle>
        <CardDescription>
          {feedback.total > 0
            ? `${feedback.total} CSV rows saved for this product.`
            : "Optional. Upload a CSV of feedback about this same product."}
        </CardDescription>
      </div>

      <form action={formAction} className="flex flex-col gap-3">
        <label htmlFor="csv-file" className="text-sm font-medium">
          CSV file
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <input
            id="csv-file"
            name="file"
            type="file"
            accept=".csv,text/csv"
            required
            className="text-sm"
          />
          <Button type="submit" disabled={pending}>
            {pending ? "Checking…" : "Upload"}
          </Button>
        </div>
        <p className="text-xs text-zinc-500">
          Required columns: feedback_id, created_at, feedback. A file with any invalid row is
          rejected and nothing from it is saved.
        </p>
        {state.saved ? (
          <p className="text-sm text-emerald-700 dark:text-emerald-300">Saved {state.saved} rows.</p>
        ) : null}
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

      {feedback.items.length ? (
        <ul className="divide-y divide-border">
          {feedback.items.map((item) => (
            <li key={item.id} className="py-3">
              <div className="flex flex-wrap items-center gap-2">
                {item.product_area ? (
                  <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                    {item.product_area}
                  </span>
                ) : null}
                {item.is_synthetic ? (
                  <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-200">
                    Synthetic seed data
                  </span>
                ) : null}
              </div>
              <p className="mt-1 text-sm text-zinc-700 dark:text-zinc-300">{item.excerpt}</p>
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}
