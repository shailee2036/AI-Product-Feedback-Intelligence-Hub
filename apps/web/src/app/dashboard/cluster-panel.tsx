"use client";

import { useActionState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

import type { ClusterReport } from "@/lib/api/types";

import { findThemes, nameThemes, type ClusterState } from "./actions";

const VISIBLE_THEMES = 8;
const VISIBLE_MEMBERS = 4;

export function ClusterPanel({ report }: { report: ClusterReport }) {
  return (
    <section className="flex flex-col gap-4 rounded-lg border border-zinc-200 p-6 dark:border-zinc-800">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Themes</h2>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{describe(report)}</p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <FindButton />
          <NameButton />
        </div>
      </div>
      {report.evaluation ? (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">{formatEvaluation(report)}</p>
      ) : null}
      {report.clusters.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {report.clusters.slice(0, VISIBLE_THEMES).map((cluster, index) => (
            <li key={cluster.id} className="text-sm">
              <span className="font-medium text-zinc-500">
                {cluster.name ?? `Theme ${index + 1}`} · {cluster.members.length} rows
              </span>
              {cluster.summary ? (
                <span className="mt-1 block text-zinc-600 dark:text-zinc-400">
                  {cluster.summary}
                </span>
              ) : null}
              <span className="mt-1 block text-zinc-800 dark:text-zinc-200">
                {cluster.members
                  .slice(0, VISIBLE_MEMBERS)
                  .map((member) => member.title)
                  .join(" · ")}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {report.cluster_count > VISIBLE_THEMES ? (
        <p className="text-xs text-zinc-500">
          Showing {VISIBLE_THEMES} of {report.cluster_count} themes.
        </p>
      ) : null}
    </section>
  );
}

function FindButton() {
  const router = useRouter();
  const [state, formAction, pending] = useActionState<ClusterState, FormData>(findThemes, {});
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
        {pending ? "Finding…" : "Find themes"}
      </button>
      {state.error ? (
        <p role="alert" className="max-w-xs text-right text-sm text-red-700 dark:text-red-300">
          {state.error}
        </p>
      ) : null}
    </form>
  );
}

function NameButton() {
  const router = useRouter();
  const [state, formAction, pending] = useActionState<ClusterState, FormData>(nameThemes, {});
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
        className="rounded-md border border-zinc-300 px-4 py-2 text-sm font-semibold text-zinc-800 hover:bg-zinc-50 disabled:opacity-60 dark:border-zinc-700 dark:text-zinc-100 dark:hover:bg-zinc-900"
      >
        {pending ? "Naming…" : "Name themes"}
      </button>
      {state.error ? (
        <p role="alert" className="max-w-xs text-right text-sm text-red-700 dark:text-red-300">
          {state.error}
        </p>
      ) : null}
    </form>
  );
}

function describe(report: ClusterReport): string {
  if (!report.ran) {
    return "Group related feedback into themes. Every original row is kept.";
  }
  if (report.named_count === 0) {
    return `${report.cluster_count} themes covering ${report.member_count} rows. Names are still blank.`;
  }
  return `${report.cluster_count} themes covering ${report.member_count} rows. ${report.named_count} named.`;
}

function formatEvaluation(report: ClusterReport): string {
  const evaluation = report.evaluation;
  if (!evaluation) return "";
  const cohesion = `${Math.round(evaluation.mean_cohesion * 100)}%`;
  return `Starter themes: ${evaluation.gathered} of ${evaluation.labeled} kept most of their members together. Average cohesion ${cohesion}.`;
}
