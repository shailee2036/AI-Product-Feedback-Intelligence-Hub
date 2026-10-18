import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Button } from "@/components/ui/button";

import { ThemeDetail } from "../../cluster-panel";
import { EmptyProduct } from "../../empty-product";
import { loadWorkspace } from "../../load";
import { WorkspaceError } from "../../workspace-error";

export const metadata: Metadata = { title: "Theme · Feedback Intelligence Hub" };

export default async function ThemeDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await loadWorkspace();
  if ("error" in data) return <WorkspaceError message={data.error} />;
  if (!data.product) return <EmptyProduct />;
  const report = data.clusters;
  const cluster = report?.clusters.find((item) => item.id === id);
  if (!report || !cluster) notFound();

  return (
    <div className="flex flex-col gap-6">
      <Button asChild variant="ghost" size="sm" className="-ml-3 w-fit">
        <Link href="/dashboard/themes">Back to themes</Link>
      </Button>
      <ThemeDetail
        cluster={cluster}
        others={report.clusters.filter((item) => item.id !== cluster.id)}
      />
    </div>
  );
}
