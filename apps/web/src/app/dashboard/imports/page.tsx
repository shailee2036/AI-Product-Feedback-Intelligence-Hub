import type { Metadata } from "next";

import { CsvPanel } from "../csv-panel";
import { EmptyProduct } from "../empty-product";
import { ImportPanel } from "../import-panel";
import { loadWorkspace } from "../load";
import { WorkspaceError } from "../workspace-error";

export const metadata: Metadata = { title: "Imports · Feedback Intelligence Hub" };

export default async function ImportsPage() {
  const data = await loadWorkspace();
  if ("error" in data) return <WorkspaceError message={data.error} />;
  if (!data.product) return <EmptyProduct />;

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Imports</h1>
        <p className="mt-1 text-sm text-muted">
          Pull public GitHub issues and optionally add a CSV for the same product.
        </p>
      </div>
      <ImportPanel job={data.job} feedback={data.feedback} />
      <CsvPanel feedback={data.csvFeedback} />
    </div>
  );
}
