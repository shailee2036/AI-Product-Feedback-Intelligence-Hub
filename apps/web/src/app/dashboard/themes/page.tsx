import type { Metadata } from "next";

import { ClusterPanel } from "../cluster-panel";
import { EmptyProduct } from "../empty-product";
import { loadWorkspace } from "../load";
import { WorkspaceError } from "../workspace-error";

export const metadata: Metadata = { title: "Themes · Feedback Intelligence Hub" };

export default async function ThemesPage() {
  const data = await loadWorkspace();
  if ("error" in data) return <WorkspaceError message={data.error} />;
  if (!data.product) return <EmptyProduct />;

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Themes</h1>
        <p className="mt-1 text-sm text-muted">
          Group related feedback, then open a theme to name, approve, and brief it.
        </p>
      </div>
      {data.clusters ? <ClusterPanel report={data.clusters} /> : (
        <p className="text-sm text-muted">Embed feedback before finding themes.</p>
      )}
    </div>
  );
}
