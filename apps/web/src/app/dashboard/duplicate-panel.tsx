"use client";

import { useActionState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

import type { DuplicateReport } from "@/lib/api/types";

import { findDuplicateFeedback, type DuplicateState } from "./actions";

const VISIBLE_GROUPS = 8;

export function DuplicatePanel({ report }: { report: DuplicateReport }) {
  return (
    <section className="flex flex-col gap-4 rounded-lg border border-zinc-200 p-6 dark:border-zinc-800">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Duplicates</h2>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{describe(report)}</p>
        </div>
        <FindButton />
      </div>
      {report.evaluation ? (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">{formatEvaluation(report)}</p>
      ) : null}
      {report.groups.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {report.groups.slice(0, VISIBLE_GROUPS).map((group) => (
            <li key={group.members.map((member) => member.id).join()} className="text-sm">
              <span className="font-medium capitalize text-zinc-500">{group.kind}</span>
              <span className="mt-1 block text-zinc-800 dark:text-zinc-200">
                {group.members.map((member) => member.title).join(" · ")}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {report.group_count > VISIBLE_GROUPS ? (
        <p className="text-xs text-zinc-500">
          Showing {VISIBLE_GROUPS} of {report.group_count} groups.
        </p>
      ) : null}
    </section>
  );
}

function FindButton() {
  const router = useRouter();
  const [state, formAction, pending] = useActionState<DuplicateState, FormData>(
    findDuplicateFeedback,
    {},
  );
  const wasPending = useRef(false);
  useEffect(() => {
    if (wasPending.current && !pending) router.refresh();
    wasPending.current = pending;
  }, [pending, router]);
  return (
    <form action={formAction} className="flex flex-col items-end gap-2">
      <button
        type="submit"
        disabled={pending}
        className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-60"
      >
        {pending ? "Finding…" : "Find duplicates"}
      </button>
      {state.error ? (
        <p role="alert" className="max-w-xs text-right text-sm text-red-700 dark:text-red-300">
          {state.error}
        </p>
      ) : null}
    </form>
  );
}

function describe(report: DuplicateReport): string {
  if (!report.ran) {
    return "Find feedback that says the same thing. Every original row is kept.";
  }
  return `${report.exact_edges} exact and ${report.semantic_edges} similar links, in ${report.group_count} groups.`;
}

function formatEvaluation(report: DuplicateReport): string {
  const evaluation = report.evaluation;
  if (!evaluation) return "";
  const known = evaluation.true_positives + evaluation.false_negatives;
  const precision = percent(evaluation.precision);
  const recall = percent(evaluation.recall);
  return `Starter labels: precision ${precision}, recall ${recall}. ${evaluation.true_positives} of ${known} known duplicates found.`;
}

function percent(value: number | null): string {
  if (value === null) return "n/a";
  return `${Math.round(value * 100)}%`;
}
