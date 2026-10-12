"use client";

import { useActionState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

import type { ClusterReport } from "@/lib/api/types";

import { decideTheme, findThemes, mergeTheme, nameThemes, renameTheme, splitTheme, writeBrief, type ClusterState } from "./actions";

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
        <ul className="flex flex-col gap-4">
          {report.clusters.slice(0, VISIBLE_THEMES).map((cluster, index) => (
            <ThemeRow
              key={cluster.id}
              cluster={cluster}
              index={index}
              others={report.clusters.filter((other) => other.id !== cluster.id)}
            />
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

function ThemeRow({
  cluster,
  index,
  others,
}: {
  cluster: ClusterReport["clusters"][number];
  index: number;
  others: ClusterReport["clusters"];
}) {
  const label = cluster.name ?? `Theme ${index + 1}`;
  return (
    <li className="flex flex-col gap-2 text-sm">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="font-medium text-zinc-800 dark:text-zinc-100">{label}</span>
        <span className="text-zinc-500">
          {statusLabel(cluster.status)} · {cluster.members.length} rows
        </span>
      </div>
      {cluster.summary ? (
        <span className="text-zinc-600 dark:text-zinc-400">{cluster.summary}</span>
      ) : null}
      <span className="text-zinc-500">{scoreLine(cluster.score)}</span>
      {cluster.brief ? <BriefDetails cluster={cluster} /> : null}
      <span className="text-zinc-800 dark:text-zinc-200">
        {cluster.members
          .slice(0, VISIBLE_MEMBERS)
          .map((member) => member.title)
          .join(" · ")}
      </span>
      <RenameForm clusterId={cluster.id} name={cluster.name ?? ""} summary={cluster.summary ?? ""} />
      <div className="flex flex-wrap items-start gap-2">
        <DecisionForm clusterId={cluster.id} decision="approve" label="Approve" />
        <DecisionForm clusterId={cluster.id} decision="dismiss" label="Dismiss" />
        {cluster.status === "approved" ? (
          <BriefForm clusterId={cluster.id} rewrite={cluster.brief !== null} />
        ) : null}
        {others.length > 0 ? <MergeForm clusterId={cluster.id} others={others} /> : null}
      </div>
      <SplitForm cluster={cluster} />
    </li>
  );
}

function RenameForm({
  clusterId,
  name,
  summary,
}: {
  clusterId: string;
  name: string;
  summary: string;
}) {
  const router = useRouter();
  const [state, formAction, pending] = useActionState(renameTheme, {});
  const wasPending = useRef(false);
  useEffect(() => {
    if (wasPending.current && !pending) router.refresh();
    wasPending.current = pending;
  }, [pending, router]);
  return (
    <form action={formAction} className="flex flex-col gap-2">
      <input type="hidden" name="clusterId" value={clusterId} />
      <input
        name="name"
        defaultValue={name}
        maxLength={80}
        aria-label="Theme name"
        className="rounded-md border border-zinc-300 px-2 py-1 dark:border-zinc-700 dark:bg-zinc-950"
      />
      <input
        name="summary"
        defaultValue={summary}
        maxLength={400}
        aria-label="Theme summary"
        className="rounded-md border border-zinc-300 px-2 py-1 dark:border-zinc-700 dark:bg-zinc-950"
      />
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={pending}
          className="rounded-md border border-zinc-300 px-3 py-1 text-xs font-semibold dark:border-zinc-700"
        >
          {pending ? "Saving…" : "Save name"}
        </button>
        {state.error ? (
          <p role="alert" className="text-xs text-red-700 dark:text-red-300">
            {state.error}
          </p>
        ) : null}
      </div>
    </form>
  );
}

function DecisionForm({
  clusterId,
  decision,
  label,
}: {
  clusterId: string;
  decision: "approve" | "dismiss";
  label: string;
}) {
  const router = useRouter();
  const [state, formAction, pending] = useActionState(decideTheme, {});
  const wasPending = useRef(false);
  useEffect(() => {
    if (wasPending.current && !pending) router.refresh();
    wasPending.current = pending;
  }, [pending, router]);
  return (
    <form action={formAction} className="flex items-center gap-2">
      <input type="hidden" name="clusterId" value={clusterId} />
      <input type="hidden" name="decision" value={decision} />
      <button
        type="submit"
        disabled={pending}
        className="rounded-md border border-zinc-300 px-3 py-1 text-xs font-semibold dark:border-zinc-700"
      >
        {label}
      </button>
      {state.error ? (
        <p role="alert" className="text-xs text-red-700 dark:text-red-300">
          {state.error}
        </p>
      ) : null}
    </form>
  );
}

function BriefForm({ clusterId, rewrite }: { clusterId: string; rewrite: boolean }) {
  const router = useRouter();
  const [state, formAction, pending] = useActionState(writeBrief, {});
  const wasPending = useRef(false);
  useEffect(() => {
    if (wasPending.current && !pending) router.refresh();
    wasPending.current = pending;
  }, [pending, router]);
  const label = pending ? "Writing…" : "Write brief";
  return (
    <form action={formAction} className="flex items-center gap-2">
      <input type="hidden" name="clusterId" value={clusterId} />
      <button
        type="submit"
        disabled={pending}
        className="rounded-md border border-zinc-300 px-3 py-1 text-xs font-semibold dark:border-zinc-700"
      >
        {rewrite && !pending ? "Rewrite brief" : label}
      </button>
      {state.error ? (
        <p role="alert" className="text-xs text-red-700 dark:text-red-300">
          {state.error}
        </p>
      ) : null}
    </form>
  );
}

function BriefDetails({ cluster }: { cluster: ClusterReport["clusters"][number] }) {
  const brief = cluster.brief;
  if (!brief) return null;
  const cited = new Set(brief.evidence_ids);
  const titles = cluster.members
    .filter((member) => cited.has(member.id))
    .map((member) => member.title);
  return (
    <div className="flex flex-col gap-1 text-zinc-600 dark:text-zinc-400">
      <span>{brief.problem}</span>
      <span>Impact: {brief.impact}</span>
      <span>Evidence: {brief.evidence_summary}</span>
      <span>Non-goals: {brief.non_goals}</span>
      <span>Acceptance: {brief.acceptance_criteria}</span>
      <span>Open questions: {brief.open_questions}</span>
      {titles.length > 0 ? <span>Cited rows: {titles.join(" · ")}</span> : null}
    </div>
  );
}

function MergeForm({
  clusterId,
  others,
}: {
  clusterId: string;
  others: ClusterReport["clusters"];
}) {
  const router = useRouter();
  const [state, formAction, pending] = useActionState(mergeTheme, {});
  const wasPending = useRef(false);
  useEffect(() => {
    if (wasPending.current && !pending) router.refresh();
    wasPending.current = pending;
  }, [pending, router]);
  return (
    <form action={formAction} className="flex items-center gap-2">
      <input type="hidden" name="clusterId" value={clusterId} />
      <select
        name="targetId"
        aria-label="Theme to merge into"
        className="rounded-md border border-zinc-300 px-2 py-1 text-xs dark:border-zinc-700 dark:bg-zinc-950"
      >
        {others.map((other, index) => (
          <option key={other.id} value={other.id}>
            {other.name ?? `Theme ${index + 1}`}
          </option>
        ))}
      </select>
      <button
        type="submit"
        disabled={pending}
        className="rounded-md border border-zinc-300 px-3 py-1 text-xs font-semibold dark:border-zinc-700"
      >
        Merge
      </button>
      {state.error ? (
        <p role="alert" className="text-xs text-red-700 dark:text-red-300">
          {state.error}
        </p>
      ) : null}
    </form>
  );
}

function SplitForm({ cluster }: { cluster: ClusterReport["clusters"][number] }) {
  const router = useRouter();
  const [state, formAction, pending] = useActionState(splitTheme, {});
  const wasPending = useRef(false);
  useEffect(() => {
    if (wasPending.current && !pending) router.refresh();
    wasPending.current = pending;
  }, [pending, router]);
  if (cluster.members.length < 2) return null;
  return (
    <form action={formAction} className="flex flex-col gap-1">
      <input type="hidden" name="clusterId" value={cluster.id} />
      {cluster.members.map((member) => (
        <label key={member.id} className="flex items-center gap-2 text-xs text-zinc-600 dark:text-zinc-400">
          <input type="checkbox" name="memberId" value={member.id} />
          {member.title}
        </label>
      ))}
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={pending}
          className="rounded-md border border-zinc-300 px-3 py-1 text-xs font-semibold dark:border-zinc-700"
        >
          {pending ? "Splitting…" : "Split selected"}
        </button>
        {state.error ? (
          <p role="alert" className="text-xs text-red-700 dark:text-red-300">
            {state.error}
          </p>
        ) : null}
      </div>
    </form>
  );
}

function statusLabel(status: ClusterReport["clusters"][number]["status"]): string {
  if (status === "approved") return "Approved";
  if (status === "dismissed") return "Dismissed";
  return "Open";
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
  const scores =
    " Each score averages size, recent rows, source mix, duplicate-adjusted volume, and completeness.";
  if (report.named_count === 0) {
    return `${report.cluster_count} themes covering ${report.member_count} rows. Names are still blank.${scores}`;
  }
  return `${report.cluster_count} themes covering ${report.member_count} rows. ${report.named_count} named. ${report.approved_count} approved.${scores}`;
}

function scoreLine(score: ClusterReport["clusters"][number]["score"]): string {
  const percent = Math.round(score.score * 100);
  const sources = score.source_count === 1 ? "1 source" : `${score.source_count} sources`;
  const name = score.named ? "named" : "unnamed";
  return `Score ${percent}%. ${score.member_count} rows · ${score.recent_count} in the last ${score.recent_days} days · ${sources} · ${score.unique_count} after duplicates · ${score.embedded_count} embedded · ${name}`;
}

function formatEvaluation(report: ClusterReport): string {
  const evaluation = report.evaluation;
  if (!evaluation) return "";
  const cohesion = `${Math.round(evaluation.mean_cohesion * 100)}%`;
  return `Starter themes: ${evaluation.gathered} of ${evaluation.labeled} kept most of their members together. Average cohesion ${cohesion}.`;
}
