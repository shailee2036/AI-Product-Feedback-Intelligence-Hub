"use client";

import { useActionState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

import type { ClusterReport } from "@/lib/api/types";

import { confirmIssueDraft, decideTheme, editBrief, findThemes, mergeTheme, nameThemes, previewIssueDraft, renameTheme, saveSuggestion, splitTheme, writeBrief, type ClusterState } from "./actions";

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
      <CanonicalIssue cluster={cluster} />
      <NewIssueDraft cluster={cluster} />
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
      <span>
        Version {brief.version} · {brief.source === "edited" ? "edited" : "generated"}
      </span>
      {brief.history.map((version) => (
        <span key={version.version}>
          Version {version.version} · {version.source === "edited" ? "edited" : "generated"} ·{" "}
          {version.problem}
        </span>
      ))}
      <EditBriefForm clusterId={cluster.id} brief={brief} />
    </div>
  );
}

function EditBriefForm({
  clusterId,
  brief,
}: {
  clusterId: string;
  brief: NonNullable<ClusterReport["clusters"][number]["brief"]>;
}) {
  const router = useRouter();
  const [state, formAction, pending] = useActionState(editBrief, {});
  const wasPending = useRef(false);
  useEffect(() => {
    if (wasPending.current && !pending) router.refresh();
    wasPending.current = pending;
  }, [pending, router]);
  return (
    <form action={formAction} className="mt-2 flex flex-col gap-2">
      <input type="hidden" name="clusterId" value={clusterId} />
      <BriefField name="problem" label="Problem" defaultValue={brief.problem} />
      <BriefField name="impact" label="Impact" defaultValue={brief.impact} />
      <BriefField name="evidence_summary" label="Evidence" defaultValue={brief.evidence_summary} />
      <BriefField name="non_goals" label="Non-goals" defaultValue={brief.non_goals} />
      <BriefField
        name="acceptance_criteria"
        label="Acceptance"
        defaultValue={brief.acceptance_criteria}
      />
      <BriefField name="open_questions" label="Open questions" defaultValue={brief.open_questions} />
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={pending}
          className="rounded-md border border-zinc-300 px-3 py-1 text-xs font-semibold dark:border-zinc-700"
        >
          {pending ? "Saving…" : "Save brief"}
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

function BriefField({
  name,
  label,
  defaultValue,
}: {
  name: string;
  label: string;
  defaultValue: string;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-zinc-500">
      {label}
      <textarea
        name={name}
        defaultValue={defaultValue}
        rows={2}
        className="rounded-md border border-zinc-300 px-2 py-1 text-sm text-zinc-800 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
      />
    </label>
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

function NewIssueDraft({ cluster }: { cluster: ClusterReport["clusters"][number] }) {
  const draft = cluster.new_issue;
  if (draft) {
    return (
      <div className="flex flex-col gap-1 text-zinc-600 dark:text-zinc-400">
        <DraftLabels labels={draft.labels} />
        <DraftWarnings warnings={draft.warnings} />
        <span>Saved locally. No GitHub issue was created.</span>
        {cluster.status === "approved" ? (
          <DraftEditor clusterId={cluster.id} title={draft.title} body={draft.body} />
        ) : (
          <>
            <span className="font-medium text-zinc-800 dark:text-zinc-200">{draft.title}</span>
            <span className="whitespace-pre-wrap">{draft.body}</span>
          </>
        )}
      </div>
    );
  }
  if (cluster.status !== "approved") return null;
  return <DraftPreview clusterId={cluster.id} />;
}

function DraftPreview({ clusterId }: { clusterId: string }) {
  const [state, formAction, pending] = useActionState(previewIssueDraft, {});
  return (
    <div className="flex flex-col gap-2 text-zinc-600 dark:text-zinc-400">
      {state.preview ? (
        <DraftEditor
          clusterId={clusterId}
          title={state.preview.title}
          body={state.preview.body}
          labels={state.preview.labels}
          warnings={state.preview.warnings}
        />
      ) : (
        <form action={formAction}>
          <input type="hidden" name="clusterId" value={clusterId} />
          <button
            type="submit"
            disabled={pending}
            className="rounded-md border border-zinc-300 px-3 py-1 text-xs font-semibold dark:border-zinc-700"
          >
            {pending ? "Drafting…" : "No suitable existing issue"}
          </button>
        </form>
      )}
      {state.error ? <DraftError message={state.error} /> : null}
    </div>
  );
}

function DraftEditor({
  clusterId,
  title,
  body,
  labels,
  warnings,
}: {
  clusterId: string;
  title: string;
  body: string;
  labels?: string[];
  warnings?: ClusterReport["clusters"][number]["duplicate_warnings"];
}) {
  const router = useRouter();
  const [state, formAction, pending] = useActionState(confirmIssueDraft, {});
  const wasPending = useRef(false);
  useEffect(() => {
    if (wasPending.current && !pending) router.refresh();
    wasPending.current = pending;
  }, [pending, router]);
  return (
    <form action={formAction} className="flex flex-col gap-2">
      <input type="hidden" name="clusterId" value={clusterId} />
      {warnings ? <DraftWarnings warnings={warnings} /> : null}
      {labels ? <DraftLabels labels={labels} /> : null}
      <BriefField name="title" label="New issue title" defaultValue={title} />
      <BriefField name="body" label="New issue body" defaultValue={body} />
      <label className="flex items-center gap-2 text-xs">
        <input type="checkbox" name="confirmed" value="yes" />
        I confirm this draft stays in the workspace and is not created on GitHub.
      </label>
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={pending}
          className="rounded-md border border-zinc-300 px-3 py-1 text-xs font-semibold dark:border-zinc-700"
        >
          {pending ? "Saving…" : "Save draft"}
        </button>
        {state.error ? <DraftError message={state.error} /> : null}
      </div>
    </form>
  );
}

function DraftLabels({ labels }: { labels: string[] }) {
  return (
    <span>{labels.length > 0 ? `Suggested labels: ${labels.join(", ")}` : "No extra labels suggested."}</span>
  );
}

function DraftWarnings({
  warnings,
}: {
  warnings: ClusterReport["clusters"][number]["duplicate_warnings"];
}) {
  if (warnings.length === 0) return <span>No similar open issue was found.</span>;
  return (
    <span>
      Similar open issues: <WarningList warnings={warnings} />
    </span>
  );
}

function DraftError({ message }: { message: string }) {
  return (
    <p role="alert" className="text-xs text-red-700 dark:text-red-300">
      {message}
    </p>
  );
}

function CanonicalIssue({ cluster }: { cluster: ClusterReport["clusters"][number] }) {
  const canonical = cluster.canonical;
  const warnings = cluster.duplicate_warnings;
  const gap = cluster.status === "approved" && canonical === null && warnings.length === 0;
  if (!canonical && warnings.length === 0 && !gap) return null;
  return (
    <div className="flex flex-col gap-1 text-zinc-600 dark:text-zinc-400">
      {canonical ? (
        <span>
          Canonical issue{" "}
          <IssueLink href={canonical.html_url} label={`#${canonical.number} ${canonical.title}`} />
          {` · ${canonicalLine(canonical)}`}
        </span>
      ) : (
        <span>No imported GitHub issue is in this theme.</span>
      )}
      {warnings.length > 0 ? (
        <span>
          Possible duplicates: <WarningList warnings={warnings} />
        </span>
      ) : null}
      {canonical || warnings.length > 0 ? (
        <span>Recommendation only. No GitHub issue is created, closed, or commented.</span>
      ) : null}
      {canonical && cluster.suggestion ? (
        <SuggestionDetails clusterId={cluster.id} status={cluster.status} suggestion={cluster.suggestion} />
      ) : null}
    </div>
  );
}

function SuggestionDetails({
  clusterId,
  status,
  suggestion,
}: {
  clusterId: string;
  status: ClusterReport["clusters"][number]["status"];
  suggestion: NonNullable<ClusterReport["clusters"][number]["suggestion"]>;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="whitespace-pre-wrap">{suggestion.comment}</span>
      <span>
        {suggestion.labels.length > 0
          ? `Suggested labels: ${suggestion.labels.join(", ")}`
          : "No extra labels suggested."}
      </span>
      {suggestion.saved ? (
        <span>Saved locally. Nothing was posted to GitHub.</span>
      ) : status === "approved" ? (
        <SuggestionForm clusterId={clusterId} />
      ) : (
        <span>Approve the theme to save this suggestion locally.</span>
      )}
    </div>
  );
}

function SuggestionForm({ clusterId }: { clusterId: string }) {
  const router = useRouter();
  const [state, formAction, pending] = useActionState(saveSuggestion, {});
  const wasPending = useRef(false);
  useEffect(() => {
    if (wasPending.current && !pending) router.refresh();
    wasPending.current = pending;
  }, [pending, router]);
  return (
    <form action={formAction} className="flex items-center gap-2">
      <input type="hidden" name="clusterId" value={clusterId} />
      <button
        type="submit"
        disabled={pending}
        className="rounded-md border border-zinc-300 px-3 py-1 text-xs font-semibold dark:border-zinc-700"
      >
        {pending ? "Saving…" : "Save suggestion"}
      </button>
      {state.error ? (
        <p role="alert" className="text-xs text-red-700 dark:text-red-300">
          {state.error}
        </p>
      ) : null}
    </form>
  );
}

function IssueLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium text-indigo-600 hover:underline"
    >
      {label}
    </a>
  );
}

function WarningList({
  warnings,
}: {
  warnings: ClusterReport["clusters"][number]["duplicate_warnings"];
}) {
  return (
    <>
      {warnings.map((warning, index) => (
        <span key={warning.id}>
          {index > 0 ? " · " : null}
          <IssueLink href={warning.html_url} label={`#${warning.number} ${warning.title}`} />
          {` (${Math.round(warning.similarity * 100)}% similar, ${
            warning.in_theme ? "in this theme" : "outside this theme"
          })`}
        </span>
      ))}
    </>
  );
}

function canonicalLine(
  issue: NonNullable<ClusterReport["clusters"][number]["canonical"]>,
): string {
  const updated = issue.recent
    ? `updated in the last ${issue.recent_days} days`
    : `not updated in the last ${issue.recent_days} days`;
  return [
    issue.state,
    `score ${Math.round(issue.score * 100)}%`,
    `coverage ${Math.round(issue.coverage * 100)}%`,
    `${issue.comment_count} comments`,
    `${issue.reactions_total} reactions`,
    updated,
  ].join(" · ");
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
