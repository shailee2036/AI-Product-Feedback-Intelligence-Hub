import type { Metadata } from "next";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";

import { EmptyProduct } from "./empty-product";
import { loadWorkspace } from "./load";
import { OverviewCharts } from "./overview-charts";
import { WorkspaceError } from "./workspace-error";

export const metadata: Metadata = { title: "Overview · Feedback Intelligence Hub" };

export default async function OverviewPage() {
  const data = await loadWorkspace();
  if ("error" in data) return <WorkspaceError message={data.error} />;
  if (!data.product) return <EmptyProduct />;

  const themes = data.clusters?.clusters ?? [];
  const chartThemes = themes.slice(0, 6).map((theme, index) => ({
    name: theme.name ?? `Theme ${index + 1}`,
    score: Math.round(theme.score.score * 100),
  }));

  return (
    <div className="flex flex-col gap-8">
      <div>
        <p className="text-sm font-medium text-accent">Registered product</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">{data.product.name}</h1>
        <a
          href={data.product.repository.html_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-accent hover:underline"
        >
          {data.product.repository.full_name}
        </a>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="GitHub issues" value={data.feedback.total} tint="bg-teal-soft" />
        <Stat label="CSV rows" value={data.csvFeedback.total} tint="bg-coral-soft" />
        <Stat label="Themes" value={data.clusters?.cluster_count ?? 0} tint="bg-violet-soft" />
        <Stat
          label="Approved"
          value={data.clusters?.approved_count ?? 0}
          hint={data.job ? `Import ${data.job.status}` : "No import yet"}
          tint="bg-gold-soft"
        />
      </div>

      <Card className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle>Import status</CardTitle>
          <CardDescription>
            {data.job
              ? `${data.job.status}: ${data.job.imported_count} imported, ${data.job.skipped_count} skipped.`
              : "Import public issues, then embed and group them into themes."}
          </CardDescription>
        </div>
        <div className="flex flex-wrap gap-2">
          {data.job ? <Badge tone={jobTone(data.job.status)}>{data.job.status}</Badge> : null}
          <Button asChild variant="secondary">
            <Link href="/dashboard/imports">Open imports</Link>
          </Button>
        </div>
      </Card>

      <OverviewCharts github={data.feedback.total} csv={data.csvFeedback.total} themes={chartThemes} />
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
  tint,
}: {
  label: string;
  value: number;
  hint?: string;
  tint: string;
}) {
  return (
    <Card className={tint}>
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-2 text-3xl font-semibold tracking-tight">{value}</p>
      {hint ? <p className="mt-1 text-xs text-muted">{hint}</p> : null}
    </Card>
  );
}

function jobTone(status: string): "success" | "warning" | "danger" | "accent" | "neutral" {
  if (status === "succeeded") return "success";
  if (status === "failed") return "danger";
  if (status === "running" || status === "queued") return "accent";
  if (status === "cancelled") return "warning";
  return "neutral";
}
