import type { Metadata } from "next";

import { DuplicatePanel } from "../duplicate-panel";
import { EmbeddingPanel } from "../embedding-panel";
import { EmptyProduct } from "../empty-product";
import { loadWorkspace } from "../load";
import { WorkspaceError } from "../workspace-error";

export const metadata: Metadata = { title: "Analysis · Feedback Intelligence Hub" };

export default async function AnalysisPage() {
  const data = await loadWorkspace();
  if ("error" in data) return <WorkspaceError message={data.error} />;
  if (!data.product) return <EmptyProduct />;

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Analysis</h1>
        <p className="mt-1 text-sm text-muted">
          Embed redacted feedback, then find exact and similar duplicates.
        </p>
      </div>
      {data.embeddings ? <EmbeddingPanel status={data.embeddings} /> : (
        <p className="text-sm text-muted">Import feedback before embedding.</p>
      )}
      {data.duplicates ? <DuplicatePanel report={data.duplicates} /> : null}
    </div>
  );
}
